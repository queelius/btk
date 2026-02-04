"""
YAML parser for view definitions.

Parses view definitions from YAML format into View objects.
Supports the full DSL including primitives, composites, and abstractions.

Example YAML:

    blog_posts:
      select:
        tags:
          any: [blog, writing]
      order: added desc
      limit: 100

    featured:
      extends: blog_posts
      select:
        field: stars
        op: gt
        value: 3
      override:
        - set:
            category: "Featured Post"
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from btk.views.core import View
from btk.views.predicates import (
    Predicate,
    TagsPredicate,
    FieldPredicate,
    TemporalPredicate,
    DomainPredicate,
    SearchPredicate,
    IdsPredicate,
    CompoundPredicate,
)
from btk.views.primitives import (
    AllView,
    SelectView,
    OrderView,
    OrderSpec,
    LimitView,
    OffsetView,
    SliceView,
    OverrideView,
    OverrideRule,
    GroupView,
    GroupSpec,
    RandomOrderView,
)
from btk.views.composites import (
    PipelineView,
    UnionView,
    IntersectView,
    DifferenceView,
    RefView,
)


class ViewParseError(Exception):
    """Error parsing view definition."""
    pass


def parse_views_file(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Parse a YAML file containing view definitions.

    Args:
        path: Path to YAML file

    Returns:
        Dictionary mapping view names to parsed view definitions
    """
    path = Path(path)

    if not path.exists():
        raise ViewParseError(f"Views file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ViewParseError(f"Views file must contain a dictionary, got {type(data)}")

    return data


def parse_view(definition: Dict[str, Any], registry: Optional["ViewRegistry"] = None) -> View:
    """
    Parse a single view definition into a View object.

    Args:
        definition: Dictionary containing view definition
        registry: Optional registry for resolving view references

    Returns:
        Parsed View object
    """
    parser = ViewParser(registry)
    return parser.parse(definition)


class ViewParser:
    """
    Parser for view definitions.

    Handles the full DSL syntax including:
    - Primitives: select, order, limit, offset, override, group
    - Composites: union, intersect, difference, pipeline
    - Abstractions: extends, params, mixins
    """

    def __init__(self, registry: Optional["ViewRegistry"] = None):
        self.registry = registry

    def parse(self, definition: Dict[str, Any]) -> View:
        """Parse a view definition into a View object."""
        if not isinstance(definition, dict):
            raise ViewParseError(f"View definition must be a dictionary, got {type(definition)}")

        # Build pipeline of operations
        stages: List[View] = []

        # Handle 'extends' - reference to base view
        if "extends" in definition:
            base_name = definition["extends"]
            stages.append(RefView(name=base_name))
        else:
            # Start with all bookmarks if no base
            stages.append(AllView())

        # Handle composite operations (these replace the base)
        if "union" in definition:
            return self._parse_union(definition["union"])

        if "intersect" in definition:
            return self._parse_intersect(definition["intersect"])

        if "difference" in definition:
            return self._parse_difference(definition["difference"])

        if "pipeline" in definition:
            return self._parse_pipeline(definition["pipeline"])

        # Handle primitive operations (these extend the pipeline)

        # Select/filter
        if "select" in definition:
            predicate = self._parse_select(definition["select"])
            stages.append(SelectView(predicate))

        # Order/sort
        if "order" in definition:
            order_view = self._parse_order(definition["order"])
            stages.append(order_view)

        # Limit
        if "limit" in definition:
            stages.append(LimitView(int(definition["limit"])))

        # Offset
        if "offset" in definition:
            stages.append(OffsetView(int(definition["offset"])))

        # Slice (offset + limit together)
        if "slice" in definition:
            slice_def = definition["slice"]
            offset = slice_def.get("offset", 0)
            limit = slice_def.get("limit")
            stages.append(SliceView(offset=offset, limit=limit))

        # Override
        if "override" in definition:
            override_view = self._parse_override(definition["override"])
            stages.append(override_view)

        # Group
        if "group" in definition:
            group_view = self._parse_group(definition["group"])
            stages.append(group_view)

        # Build final view
        if len(stages) == 1:
            return stages[0]

        return PipelineView(stages)

    def _parse_select(self, select_def: Any) -> Predicate:
        """Parse select/filter definition into a Predicate."""
        if isinstance(select_def, list):
            # List of conditions - AND them together
            predicates = [self._parse_predicate(p) for p in select_def]
            return CompoundPredicate(operator="all", predicates=predicates)

        if isinstance(select_def, dict):
            return self._parse_predicate(select_def)

        raise ViewParseError(f"Invalid select definition: {select_def}")

    def _parse_predicate(self, pred_def: Dict[str, Any]) -> Predicate:
        """Parse a predicate definition."""
        # Compound predicates
        if "all" in pred_def:
            predicates = [self._parse_predicate(p) for p in pred_def["all"]]
            return CompoundPredicate(operator="all", predicates=predicates)

        if "any" in pred_def:
            predicates = [self._parse_predicate(p) for p in pred_def["any"]]
            return CompoundPredicate(operator="any", predicates=predicates)

        if "not" in pred_def:
            inner = self._parse_predicate(pred_def["not"])
            return CompoundPredicate(operator="not", predicates=[inner])

        # Tags predicate
        if "tags" in pred_def:
            tags_def = pred_def["tags"]
            if isinstance(tags_def, list):
                # Simple list: all tags required
                return TagsPredicate(tags=tags_def, mode="all")
            elif isinstance(tags_def, dict):
                if "all" in tags_def:
                    return TagsPredicate(tags=tags_def["all"], mode="all")
                if "any" in tags_def:
                    return TagsPredicate(tags=tags_def["any"], mode="any")
                if "none" in tags_def:
                    return TagsPredicate(tags=tags_def["none"], mode="none")
                if "match" in tags_def:
                    return TagsPredicate(tags=[tags_def["match"]], mode="match")
            else:
                # Single tag string
                return TagsPredicate(tags=[str(tags_def)], mode="all")

        # Field predicate
        if "field" in pred_def:
            field_name = pred_def["field"]
            op = pred_def.get("op", "eq")
            value = pred_def.get("value")
            return FieldPredicate(field=field_name, operator=op, value=value)

        # Temporal predicates
        if "added" in pred_def:
            return self._parse_temporal("added", pred_def["added"])

        if "visited" in pred_def:
            return self._parse_temporal("visited", pred_def["visited"])

        if "last_visited" in pred_def:
            return self._parse_temporal("last_visited", pred_def["last_visited"])

        # Domain predicate
        if "domain" in pred_def:
            domain_def = pred_def["domain"]
            if isinstance(domain_def, list):
                return DomainPredicate(domains=domain_def)
            else:
                return DomainPredicate(domains=[str(domain_def)])

        # Search predicate
        if "search" in pred_def:
            search_def = pred_def["search"]
            if isinstance(search_def, dict):
                query = search_def.get("query", "")
                fields = search_def.get("fields", ["title", "description", "url"])
                return SearchPredicate(query=query, fields=fields)
            else:
                return SearchPredicate(query=str(search_def))

        # IDs predicate
        if "ids" in pred_def:
            return IdsPredicate(ids=pred_def["ids"])

        # Shorthand field predicates
        for field_name in ["stars", "pinned", "archived", "visit_count", "reachable"]:
            if field_name in pred_def:
                field_def = pred_def[field_name]
                if isinstance(field_def, dict):
                    op = field_def.get("op", "eq")
                    value = field_def.get("value")
                else:
                    # Direct value means equality
                    op = "eq"
                    value = field_def
                return FieldPredicate(field=field_name, operator=op, value=value)

        # Unknown predicate type - try to infer
        if len(pred_def) == 1:
            key, value = next(iter(pred_def.items()))
            # Assume it's a field name with equality check
            return FieldPredicate(field=key, operator="eq", value=value)

        raise ViewParseError(f"Unknown predicate format: {pred_def}")

    def _parse_temporal(self, field: str, temporal_def: Any) -> TemporalPredicate:
        """Parse a temporal predicate definition."""
        if isinstance(temporal_def, dict):
            after = temporal_def.get("after")
            before = temporal_def.get("before")
            within = temporal_def.get("within")
            return TemporalPredicate(field=field, after=after, before=before, within=within)
        elif isinstance(temporal_def, str):
            # Parse relative expression like "30 days ago"
            return TemporalPredicate(field=field, after=temporal_def)
        else:
            raise ViewParseError(f"Invalid temporal definition for {field}: {temporal_def}")

    def _parse_order(self, order_def: Any) -> View:
        """Parse order definition into an OrderView."""
        if isinstance(order_def, str):
            # Parse string format: "field1 desc, field2 asc"
            if order_def.strip().lower() == "random":
                return RandomOrderView()
            return OrderView.from_string(order_def)

        if isinstance(order_def, list):
            # List of order specs
            specs = []
            for spec in order_def:
                if isinstance(spec, str):
                    parts = spec.split()
                    field = parts[0]
                    direction = parts[1].lower() if len(parts) > 1 else "asc"
                    specs.append(OrderSpec(field=field, direction=direction))
                elif isinstance(spec, dict):
                    specs.append(OrderSpec(
                        field=spec["field"],
                        direction=spec.get("direction", "asc"),
                        nulls=spec.get("nulls", "last"),
                        case_sensitive=spec.get("case_sensitive", False)
                    ))
            return OrderView(specs)

        if isinstance(order_def, dict):
            if order_def.get("random"):
                seed = order_def.get("seed")
                return RandomOrderView(seed=seed)

            specs = [OrderSpec(
                field=order_def["field"],
                direction=order_def.get("direction", "asc"),
                nulls=order_def.get("nulls", "last"),
                case_sensitive=order_def.get("case_sensitive", False)
            )]
            return OrderView(specs)

        raise ViewParseError(f"Invalid order definition: {order_def}")

    def _parse_override(self, override_def: Any) -> OverrideView:
        """Parse override definition into an OverrideView."""
        rules = []

        if isinstance(override_def, dict):
            # Single rule or global settings
            if "set" in override_def:
                match_pred = None
                if "match" in override_def:
                    match_pred = self._parse_predicate(override_def["match"])
                rules.append(OverrideRule(
                    match=match_pred,
                    set_fields=override_def["set"]
                ))
            else:
                # Assume it's all set fields
                rules.append(OverrideRule(match=None, set_fields=override_def))

        elif isinstance(override_def, list):
            # List of rules
            for rule_def in override_def:
                match_pred = None
                if "match" in rule_def:
                    match_pred = self._parse_predicate(rule_def["match"])

                set_fields = rule_def.get("set", {})
                rules.append(OverrideRule(match=match_pred, set_fields=set_fields))

        return OverrideView(rules)

    def _parse_group(self, group_def: Any) -> GroupView:
        """Parse group definition into a GroupView."""
        if isinstance(group_def, str):
            # Simple field name
            return GroupView(GroupSpec(field=group_def))

        if isinstance(group_def, dict):
            field = group_def.get("by", group_def.get("field"))
            if not field:
                raise ViewParseError("Group definition must specify 'by' or 'field'")

            return GroupView(GroupSpec(
                field=field,
                granularity=group_def.get("granularity"),
                strategy=group_def.get("strategy", "primary"),
                order=group_def.get("order", "asc"),
                min_count=group_def.get("min_count", 0)
            ))

        raise ViewParseError(f"Invalid group definition: {group_def}")

    def _parse_union(self, union_def: List[Any]) -> UnionView:
        """Parse union definition."""
        views = []
        for view_def in union_def:
            if isinstance(view_def, str):
                # Reference to named view
                views.append(RefView(name=view_def))
            elif isinstance(view_def, dict):
                views.append(self.parse(view_def))
            else:
                raise ViewParseError(f"Invalid union member: {view_def}")

        return UnionView(views)

    def _parse_intersect(self, intersect_def: List[Any]) -> IntersectView:
        """Parse intersect definition."""
        views = []
        for view_def in intersect_def:
            if isinstance(view_def, str):
                views.append(RefView(name=view_def))
            elif isinstance(view_def, dict):
                views.append(self.parse(view_def))
            else:
                raise ViewParseError(f"Invalid intersect member: {view_def}")

        return IntersectView(views)

    def _parse_difference(self, diff_def: Dict[str, Any]) -> DifferenceView:
        """Parse difference definition."""
        if "from" not in diff_def:
            raise ViewParseError("Difference must specify 'from' (primary view)")

        if "exclude" not in diff_def:
            raise ViewParseError("Difference must specify 'exclude' (excluded views)")

        primary_def = diff_def["from"]
        if isinstance(primary_def, str):
            primary = RefView(name=primary_def)
        else:
            primary = self.parse(primary_def)

        exclude_defs = diff_def["exclude"]
        if not isinstance(exclude_defs, list):
            exclude_defs = [exclude_defs]

        excluded = []
        for exc_def in exclude_defs:
            if isinstance(exc_def, str):
                excluded.append(RefView(name=exc_def))
            else:
                excluded.append(self.parse(exc_def))

        return DifferenceView(primary=primary, excluded=excluded)

    def _parse_pipeline(self, pipeline_def: List[Any]) -> PipelineView:
        """Parse pipeline definition."""
        stages = []
        for stage_def in pipeline_def:
            if isinstance(stage_def, str):
                stages.append(RefView(name=stage_def))
            elif isinstance(stage_def, dict):
                stages.append(self.parse(stage_def))
            else:
                raise ViewParseError(f"Invalid pipeline stage: {stage_def}")

        return PipelineView(stages)
