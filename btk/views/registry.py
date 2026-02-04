"""
View Registry - named view management.

The registry stores and resolves named views, enabling:
- View definitions from YAML files
- Programmatic view registration
- View reference resolution
- Parameterized view instantiation
- Built-in default views
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from btk.views.core import View, ViewContext, ViewResult
from btk.views.parser import ViewParser, parse_views_file


class ViewNotFoundError(Exception):
    """Raised when a view is not found in the registry."""
    pass


class ViewRegistry:
    """
    Registry for named views.

    Provides:
    - Loading views from YAML files
    - Programmatic view registration
    - View resolution with parameter substitution
    - Built-in views for common patterns
    - View discovery and listing

    Example:
        registry = ViewRegistry()
        registry.load_file("btk-views.yaml")

        view = registry.get("blog_featured")
        result = view.evaluate(db, ViewContext(registry=registry))

        # With parameters
        view = registry.get("recent_by_tag", tag="python", days=30)
    """

    def __init__(self):
        self._views: Dict[str, View] = {}
        self._definitions: Dict[str, Dict[str, Any]] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._parser = ViewParser(self)

        # Register built-in views
        self._register_builtins()

    def _register_builtins(self):
        """Register built-in default views."""
        from btk.views.primitives import (
            AllView,
            SelectView,
            OrderView,
            OrderSpec,
            LimitView,
        )
        from btk.views.predicates import (
            FieldPredicate,
            TagsPredicate,
        )
        from btk.views.composites import PipelineView

        # all - all bookmarks
        self.register("all", AllView(), metadata={
            "description": "All bookmarks",
            "builtin": True
        })

        # recent - last 50 bookmarks by added date
        recent = PipelineView([
            AllView(),
            OrderView([OrderSpec("added", "desc")]),
            LimitView(50)
        ])
        self.register("recent", recent, metadata={
            "description": "50 most recently added bookmarks",
            "builtin": True
        })

        # starred - bookmarks with stars > 0
        starred = PipelineView([
            SelectView(FieldPredicate("stars", "gt", 0)),
            OrderView([OrderSpec("stars", "desc"), OrderSpec("added", "desc")])
        ])
        self.register("starred", starred, metadata={
            "description": "Starred bookmarks by star count",
            "builtin": True
        })

        # pinned - pinned bookmarks
        pinned = SelectView(FieldPredicate("pinned", "eq", True))
        self.register("pinned", pinned, metadata={
            "description": "Pinned bookmarks",
            "builtin": True
        })

        # archived - archived bookmarks
        archived = SelectView(FieldPredicate("archived", "eq", True))
        self.register("archived", archived, metadata={
            "description": "Archived bookmarks",
            "builtin": True
        })

        # unread - never visited bookmarks
        unread = SelectView(FieldPredicate("visit_count", "eq", 0))
        self.register("unread", unread, metadata={
            "description": "Never visited bookmarks",
            "builtin": True
        })

        # popular - frequently visited
        popular = PipelineView([
            SelectView(FieldPredicate("visit_count", "gt", 5)),
            OrderView([OrderSpec("visit_count", "desc")])
        ])
        self.register("popular", popular, metadata={
            "description": "Frequently visited bookmarks (>5 visits)",
            "builtin": True
        })

        # broken - unreachable URLs
        broken = SelectView(FieldPredicate("reachable", "eq", False))
        self.register("broken", broken, metadata={
            "description": "Unreachable/broken bookmarks",
            "builtin": True
        })

        # untagged - no tags
        untagged = SelectView(TagsPredicate(tags=[], mode="none"))
        self.register("untagged", untagged, metadata={
            "description": "Bookmarks without tags",
            "builtin": True
        })

    def register(
        self,
        name: str,
        view: View,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Register a view by name.

        Args:
            name: View name (unique identifier)
            view: View object
            metadata: Optional metadata (description, builtin flag, etc.)
        """
        self._views[name] = view
        self._metadata[name] = metadata or {}

    def register_definition(
        self,
        name: str,
        definition: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Register a view definition (parsed on first access).

        This allows lazy parsing and supports parameterized views.

        Args:
            name: View name
            definition: Raw definition dictionary
            metadata: Optional metadata
        """
        self._definitions[name] = definition
        self._metadata[name] = metadata or {}

        # Extract metadata from definition if present
        if "description" in definition:
            self._metadata[name]["description"] = definition["description"]
        if "params" in definition:
            self._metadata[name]["params"] = definition["params"]

    def get(self, name: str, **params) -> View:
        """
        Get a view by name.

        Args:
            name: View name
            **params: Parameters for parameterized views

        Returns:
            View object

        Raises:
            ViewNotFoundError: If view is not found
        """
        # Check compiled views first
        if name in self._views:
            return self._views[name]

        # Check definitions (parse on demand)
        if name in self._definitions:
            view = self._parse_definition(name, params)
            # Cache non-parameterized views
            if not params and not self._metadata.get(name, {}).get("params"):
                self._views[name] = view
            return view

        raise ViewNotFoundError(f"View not found: {name}")

    def _parse_definition(self, name: str, params: Dict[str, Any]) -> View:
        """Parse and return a view from its definition."""
        definition = self._definitions[name].copy()

        # Apply parameter defaults
        if "params" in definition:
            defaults = definition.pop("params")
            for key, default in defaults.items():
                if key not in params:
                    params[key] = default

        # Remove metadata keys before parsing
        definition.pop("description", None)

        return self._parser.parse(definition)

    def has(self, name: str) -> bool:
        """Check if a view exists in the registry."""
        return name in self._views or name in self._definitions

    def list(self, include_builtin: bool = True) -> List[str]:
        """
        List all registered view names.

        Args:
            include_builtin: Include built-in views

        Returns:
            List of view names
        """
        names = set(self._views.keys()) | set(self._definitions.keys())

        if not include_builtin:
            names = {n for n in names if not self._metadata.get(n, {}).get("builtin")}

        return sorted(names)

    def get_metadata(self, name: str) -> Dict[str, Any]:
        """Get metadata for a view."""
        return self._metadata.get(name, {})

    def load_file(self, path: Union[str, Path]) -> int:
        """
        Load views from a YAML file.

        Args:
            path: Path to YAML file

        Returns:
            Number of views loaded
        """
        data = parse_views_file(path)
        count = 0

        for name, definition in data.items():
            if isinstance(definition, dict):
                self.register_definition(name, definition)
                count += 1

        return count

    def load_directory(self, path: Union[str, Path], pattern: str = "*.yaml") -> int:
        """
        Load views from all YAML files in a directory.

        Args:
            path: Directory path
            pattern: Glob pattern for files

        Returns:
            Total number of views loaded
        """

        path = Path(path)
        count = 0

        for yaml_path in path.glob(pattern):
            count += self.load_file(yaml_path)

        # Also check .yml extension
        for yaml_path in path.glob(pattern.replace(".yaml", ".yml")):
            count += self.load_file(yaml_path)

        return count

    def evaluate(
        self,
        name: str,
        db: "Database",
        **params
    ) -> ViewResult:
        """
        Convenience method to get and evaluate a view.

        Args:
            name: View name
            db: Database to query
            **params: View parameters

        Returns:
            ViewResult
        """
        view = self.get(name, **params)
        context = ViewContext(params=params, registry=self)
        return view.evaluate(db, context)

    def info(self) -> Dict[str, Any]:
        """
        Get registry information.

        Returns:
            Dictionary with registry stats and view list
        """
        views_info = []
        for name in self.list():
            meta = self._metadata.get(name, {})
            views_info.append({
                "name": name,
                "description": meta.get("description", ""),
                "builtin": meta.get("builtin", False),
                "has_params": bool(meta.get("params")),
            })

        return {
            "total_views": len(views_info),
            "builtin_views": sum(1 for v in views_info if v["builtin"]),
            "custom_views": sum(1 for v in views_info if not v["builtin"]),
            "views": views_info
        }

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "ViewRegistry":
        """
        Create a registry and load views from a YAML file.

        Args:
            path: Path to YAML file

        Returns:
            ViewRegistry with loaded views
        """
        registry = cls()
        registry.load_file(path)
        return registry

    def __contains__(self, name: str) -> bool:
        return self.has(name)

    def __iter__(self):
        return iter(self.list())

    def __len__(self) -> int:
        return len(self.list())
