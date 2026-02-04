"""
Simple, universal progress bar decorator for BTK.
"""
from functools import wraps
import sys
import os
from typing import Any, Callable, Optional
from rich.progress import track, Progress, SpinnerColumn, TextColumn


def with_progress(description: Optional[str] = None) -> Callable:
    """
    Universal progress decorator that automatically shows progress bars for iterations.
    
    Args:
        description: Optional description to show (defaults to function name)
    
    Returns:
        Decorated function that shows progress when iterating
    
    Example:
        @with_progress("Processing bookmarks")
        def process(bookmarks):
            for bookmark in bookmarks:
                # ... do work ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Skip progress in these cases:
            # 1. Output is not a TTY (piped/redirected)
            # 2. BTK_NO_PROGRESS environment variable is set
            # 3. User explicitly disabled with --no-progress flag (checked via kwargs)
            if (not sys.stdout.isatty() or 
                os.environ.get('BTK_NO_PROGRESS') or
                kwargs.get('no_progress', False)):
                # Remove no_progress from kwargs if present
                kwargs.pop('no_progress', None)
                return func(*args, **kwargs)
            
            # Try to find an iterable argument to track
            iterable = None
            iterable_index = None
            
            # Look through positional arguments for something iterable
            for i, arg in enumerate(args):
                # Check if it's iterable but not a string or dict
                if (hasattr(arg, '__iter__') and 
                    not isinstance(arg, (str, bytes, dict)) and
                    hasattr(arg, '__len__')):  # Only sized iterables for now
                    iterable = arg
                    iterable_index = i
                    break
            
            # If we found a trackable iterable, wrap it with progress
            if iterable is not None and iterable_index is not None:
                try:
                    # Create description
                    desc = description or f"{func.__name__.replace('_', ' ').title()}"
                    
                    # Wrap the iterable with rich.progress.track
                    tracked_iterable = track(
                        iterable, 
                        description=desc,
                        transient=True  # Remove progress bar when done
                    )
                    
                    # Replace the original iterable with the tracked one
                    new_args = list(args)
                    new_args[iterable_index] = tracked_iterable
                    
                    return func(*new_args, **kwargs)
                except Exception:
                    # If anything goes wrong with progress, just run normally
                    return func(*args, **kwargs)
            else:
                # No suitable iterable found, run normally
                return func(*args, **kwargs)
        
        # Add a method to force disable progress for this call
        wrapper.without_progress = lambda *args, **kwargs: func(*args, **kwargs)
        
        return wrapper
    return decorator


def spinner(description: Optional[str] = None) -> Callable:
    """
    Show a spinner for operations without clear progress.
    
    Args:
        description: Optional description to show
    
    Returns:
        Decorated function that shows a spinner
    
    Example:
        @spinner("Fetching data")
        def fetch_remote_data():
            # ... long operation ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if not sys.stdout.isatty() or os.environ.get('BTK_NO_PROGRESS'):
                return func(*args, **kwargs)
            
            desc = description or f"{func.__name__.replace('_', ' ').title()}"
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True
            ) as progress:
                progress.add_task(desc, total=None)
                return func(*args, **kwargs)
        
        return wrapper
    return decorator