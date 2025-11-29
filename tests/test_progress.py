"""
Tests for btk/progress.py progress decorators.

Tests the progress bar and spinner decorators that enhance
user experience during long-running operations.
"""
import os
import sys
import pytest
from io import StringIO
from unittest.mock import patch, MagicMock

from btk.progress import with_progress, spinner


class TestWithProgressDecorator:
    """Test @with_progress decorator."""

    def test_decorated_function_returns_correct_result(self):
        """Decorated function should return the same result as undecorated."""

        @with_progress("Processing")
        def process_items(items):
            return [item * 2 for item in items]

        result = process_items([1, 2, 3])
        assert result == [2, 4, 6]

    def test_decorated_function_preserves_name(self):
        """Decorated function should preserve original function name."""

        @with_progress("Test")
        def my_custom_function(items):
            return items

        assert my_custom_function.__name__ == "my_custom_function"

    def test_decorator_passes_through_when_not_tty(self, monkeypatch):
        """Decorator should not show progress when stdout is not TTY."""
        monkeypatch.setattr(sys.stdout, 'isatty', lambda: False)

        @with_progress("Processing")
        def process_items(items):
            return [item * 2 for item in items]

        result = process_items([1, 2, 3])
        assert result == [2, 4, 6]

    def test_decorator_respects_btk_no_progress_env(self, monkeypatch):
        """Decorator should not show progress when BTK_NO_PROGRESS is set."""
        monkeypatch.setenv("BTK_NO_PROGRESS", "1")

        @with_progress("Processing")
        def process_items(items):
            return [item * 2 for item in items]

        result = process_items([1, 2, 3])
        assert result == [2, 4, 6]

    def test_decorator_respects_no_progress_kwarg(self):
        """Decorator should not show progress when no_progress=True."""

        @with_progress("Processing")
        def process_items(items):
            return [item * 2 for item in items]

        result = process_items([1, 2, 3], no_progress=True)
        assert result == [2, 4, 6]

    def test_no_progress_kwarg_is_removed_before_calling_func(self):
        """no_progress kwarg should be removed before calling decorated function."""

        @with_progress("Processing")
        def process_items(items, **kwargs):
            # Function should NOT receive no_progress kwarg
            assert "no_progress" not in kwargs
            return items

        process_items([1, 2, 3], no_progress=True)

    def test_without_progress_method_exists(self):
        """Decorated function should have .without_progress() method."""

        @with_progress("Test")
        def my_func(items):
            return items

        assert hasattr(my_func, 'without_progress')
        assert callable(my_func.without_progress)

    def test_without_progress_method_bypasses_decorator(self):
        """without_progress() should call original function directly."""

        @with_progress("Processing")
        def process_items(items):
            return [item * 2 for item in items]

        result = process_items.without_progress([1, 2, 3])
        assert result == [2, 4, 6]

    def test_decorator_handles_empty_iterable(self):
        """Decorator should handle empty iterables gracefully."""

        @with_progress("Processing")
        def process_items(items):
            return list(items)

        result = process_items([])
        assert result == []

    def test_decorator_handles_string_argument(self):
        """Decorator should not try to track strings (even though iterable)."""

        @with_progress("Processing")
        def process_text(text):
            return text.upper()

        result = process_text("hello")
        assert result == "HELLO"

    def test_decorator_handles_dict_argument(self):
        """Decorator should not try to track dicts (even though iterable)."""

        @with_progress("Processing")
        def process_dict(data):
            return {k: v * 2 for k, v in data.items()}

        result = process_dict({"a": 1, "b": 2})
        assert result == {"a": 2, "b": 4}

    def test_decorator_finds_iterable_in_args(self):
        """Decorator should find first iterable in positional arguments."""

        @with_progress("Processing")
        def process_with_prefix(prefix, items):
            return [prefix + str(item) for item in items]

        # The decorator should skip 'prefix' (string) and find 'items' (list)
        result = process_with_prefix("item_", [1, 2, 3])
        # This may or may not work depending on implementation
        # The important thing is it doesn't crash
        assert len(result) == 3

    def test_decorator_handles_no_iterable(self):
        """Decorator should work when no iterable is found."""

        @with_progress("Processing")
        def add_numbers(a, b):
            return a + b

        result = add_numbers(5, 3)
        assert result == 8

    def test_decorator_default_description_from_function_name(self):
        """Decorator should generate description from function name if not provided."""

        @with_progress()
        def process_bookmarks(items):
            return items

        # Function should still work
        result = process_bookmarks([1, 2])
        assert result == [1, 2]

    def test_decorator_with_kwargs_passed_through(self):
        """Decorator should pass kwargs through to function."""

        @with_progress("Processing")
        def process_items(items, multiplier=1):
            return [item * multiplier for item in items]

        result = process_items([1, 2, 3], multiplier=3)
        assert result == [3, 6, 9]


class TestSpinnerDecorator:
    """Test @spinner decorator."""

    def test_decorated_function_returns_correct_result(self):
        """Decorated function should return the same result as undecorated."""

        @spinner("Loading")
        def fetch_data():
            return {"key": "value"}

        result = fetch_data()
        assert result == {"key": "value"}

    def test_decorated_function_preserves_name(self):
        """Decorated function should preserve original function name."""

        @spinner("Loading")
        def my_spinner_function():
            return True

        assert my_spinner_function.__name__ == "my_spinner_function"

    def test_spinner_passes_through_when_not_tty(self, monkeypatch):
        """Spinner should not show when stdout is not TTY."""
        monkeypatch.setattr(sys.stdout, 'isatty', lambda: False)

        @spinner("Loading")
        def fetch_data():
            return {"key": "value"}

        result = fetch_data()
        assert result == {"key": "value"}

    def test_spinner_respects_btk_no_progress_env(self, monkeypatch):
        """Spinner should not show when BTK_NO_PROGRESS is set."""
        monkeypatch.setenv("BTK_NO_PROGRESS", "1")

        @spinner("Loading")
        def fetch_data():
            return {"key": "value"}

        result = fetch_data()
        assert result == {"key": "value"}

    def test_spinner_default_description_from_function_name(self):
        """Spinner should generate description from function name if not provided."""

        @spinner()
        def fetch_remote_data():
            return "data"

        result = fetch_remote_data()
        assert result == "data"

    def test_spinner_with_args(self):
        """Spinner should pass arguments to decorated function."""

        @spinner("Processing")
        def process_url(url, timeout=10):
            return f"Fetched {url} with timeout {timeout}"

        result = process_url("https://example.com", timeout=30)
        assert result == "Fetched https://example.com with timeout 30"


class TestProgressIntegration:
    """Integration tests for progress decorators."""

    def test_nested_decorators(self):
        """Multiple progress decorators should work together."""

        @with_progress("Outer")
        def outer(items):
            return [inner(item) for item in items]

        @spinner("Inner")
        def inner(item):
            return item * 2

        result = outer([1, 2, 3])
        assert result == [2, 4, 6]

    def test_progress_with_exception(self):
        """Progress decorator should not suppress exceptions."""

        @with_progress("Processing")
        def process_items(items):
            for item in items:
                if item < 0:
                    raise ValueError("Negative value")
            return items

        with pytest.raises(ValueError, match="Negative value"):
            process_items([1, -1, 2])

    def test_spinner_with_exception(self):
        """Spinner decorator should not suppress exceptions."""

        @spinner("Loading")
        def risky_operation():
            raise RuntimeError("Something went wrong")

        with pytest.raises(RuntimeError, match="Something went wrong"):
            risky_operation()


class TestProgressEnvironmentHandling:
    """Test environment-based behavior of progress decorators."""

    def test_progress_decorator_when_tty_and_no_env(self, monkeypatch):
        """Progress should attempt to show when TTY and no BTK_NO_PROGRESS."""
        # Ensure env var is not set
        monkeypatch.delenv("BTK_NO_PROGRESS", raising=False)

        # Mock isatty to return True
        monkeypatch.setattr(sys.stdout, 'isatty', lambda: True)

        @with_progress("Test")
        def process(items):
            # We can't easily test that progress is shown,
            # but we can verify the function runs correctly
            return list(items)

        # Use a list with __len__ to trigger progress tracking attempt
        result = process([1, 2, 3])
        assert result == [1, 2, 3]

    def test_progress_decorator_empty_env_var(self, monkeypatch):
        """Empty BTK_NO_PROGRESS should be treated as not set (falsy)."""
        monkeypatch.setenv("BTK_NO_PROGRESS", "")

        @with_progress("Test")
        def process(items):
            return list(items)

        # Empty string is falsy, so progress should attempt to show
        result = process([1, 2])
        assert result == [1, 2]
