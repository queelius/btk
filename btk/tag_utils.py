"""
Tag utilities for hierarchical tag management.
"""
from collections import defaultdict
from typing import List, Dict, Set, Tuple


def parse_tag_hierarchy(tags: List[str], separator: str = '/') -> Dict[str, Set[str]]:
    """
    Parse flat tags into a hierarchical structure.
    
    Args:
        tags: List of tags (e.g., ['programming/python', 'programming/go', 'news/tech'])
        separator: Hierarchy separator (default: '/')
    
    Returns:
        Dictionary mapping parent tags to sets of child tags
    """
    hierarchy = defaultdict(set)
    
    for tag in tags:
        parts = tag.split(separator)
        current = ""
        
        for i, part in enumerate(parts):
            parent = current
            current = separator.join(parts[:i+1])
            
            if parent:
                hierarchy[parent].add(current)
            else:
                hierarchy['_root'].add(current)
    
    return dict(hierarchy)


def get_tag_tree(bookmarks: List[Dict], separator: str = '/') -> Dict[str, any]:
    """
    Build a tree structure of all tags in bookmarks.
    
    Args:
        bookmarks: List of bookmark dictionaries
        separator: Hierarchy separator
    
    Returns:
        Nested dictionary representing tag tree
    """
    # Collect all unique tags
    all_tags = set()
    for bookmark in bookmarks:
        all_tags.update(bookmark.get('tags', []))
    
    # Build tree structure
    tree = {}
    
    for tag in sorted(all_tags):
        parts = tag.split(separator)
        current = tree
        
        for part in parts:
            if part not in current:
                current[part] = {}
            current = current[part]
    
    return tree


def filter_bookmarks_by_tag_prefix(bookmarks: List[Dict], prefix: str, 
                                  separator: str = '/') -> List[Dict]:
    """
    Filter bookmarks that have tags starting with the given prefix.
    
    Args:
        bookmarks: List of bookmark dictionaries
        prefix: Tag prefix to filter by (e.g., 'programming')
        separator: Hierarchy separator
    
    Returns:
        Filtered list of bookmarks
    """
    # If prefix is empty, return bookmarks that have at least one tag
    if not prefix:
        return [b for b in bookmarks if b.get('tags', [])]
    
    filtered = []
    
    for bookmark in bookmarks:
        tags = bookmark.get('tags', [])
        
        # Check if any tag starts with the prefix
        for tag in tags:
            if tag.startswith(prefix):
                # Also handle exact matches and proper hierarchy
                if (tag == prefix or 
                    tag.startswith(prefix + separator)):
                    filtered.append(bookmark)
                    break
    
    return filtered


def get_tag_statistics(bookmarks: List[Dict], separator: str = '/') -> Dict[str, Dict]:
    """
    Get statistics for all tags including hierarchy.
    
    Args:
        bookmarks: List of bookmark dictionaries
        separator: Hierarchy separator
    
    Returns:
        Dictionary with tag statistics including counts at each level
    """
    # Count direct tag usage
    tag_counts = defaultdict(int)
    tag_bookmarks = defaultdict(set)
    
    for bookmark in bookmarks:
        for tag in bookmark.get('tags', []):
            tag_counts[tag] += 1
            tag_bookmarks[tag].add(bookmark.get('id', bookmark.get('unique_id')))
    
    # Calculate hierarchical counts (parent includes children)
    hierarchical_counts = defaultdict(int)
    hierarchical_bookmarks = defaultdict(set)
    
    for tag, count in tag_counts.items():
        parts = tag.split(separator)
        
        # Add count to all parent levels
        for i in range(1, len(parts) + 1):
            parent = separator.join(parts[:i])
            hierarchical_counts[parent] += count
            hierarchical_bookmarks[parent].update(tag_bookmarks[tag])
    
    # Build result
    stats = {}
    for tag in sorted(set(list(tag_counts.keys()) + list(hierarchical_counts.keys()))):
        stats[tag] = {
            'direct_count': tag_counts.get(tag, 0),
            'total_count': hierarchical_counts.get(tag, tag_counts.get(tag, 0)),
            'bookmark_count': len(hierarchical_bookmarks.get(tag, tag_bookmarks.get(tag, set())))
        }
    
    return stats


def rename_tag_hierarchy(bookmarks: List[Dict], old_tag: str, new_tag: str,
                        separator: str = '/') -> Tuple[List[Dict], int]:
    """
    Rename a tag and all its children in the hierarchy.
    
    Args:
        bookmarks: List of bookmark dictionaries
        old_tag: Tag to rename (e.g., 'programming/python')
        new_tag: New tag name (e.g., 'development/python')
        separator: Hierarchy separator
    
    Returns:
        Tuple of (updated bookmarks, number of bookmarks affected)
    
    Raises:
        ValueError: If new_tag contains the separator multiple times consecutively
    """
    # Validate new_tag doesn't have invalid patterns
    if separator * 2 in new_tag:
        raise ValueError(f"Invalid tag: '{new_tag}' contains consecutive separators")
    
    affected_count = 0
    
    for bookmark in bookmarks:
        tags = bookmark.get('tags', [])
        new_tags = []
        modified = False
        
        for tag in tags:
            # Check if tag matches exactly or is a child
            if tag == old_tag:
                new_tags.append(new_tag)
                modified = True
            elif tag.startswith(old_tag + separator):
                # Replace the prefix for child tags
                suffix = tag[len(old_tag):]
                new_tags.append(new_tag + suffix)
                modified = True
            else:
                new_tags.append(tag)
        
        if modified:
            bookmark['tags'] = new_tags
            affected_count += 1
    
    return bookmarks, affected_count


def merge_tags(bookmarks: List[Dict], source_tags: List[str], target_tag: str) -> Tuple[List[Dict], int]:
    """
    Merge multiple tags into a single target tag.
    
    Args:
        bookmarks: List of bookmark dictionaries
        source_tags: List of tags to merge from
        target_tag: Tag to merge into
    
    Returns:
        Tuple of (updated bookmarks, number of bookmarks affected)
    """
    affected_count = 0
    source_set = set(source_tags)
    
    for bookmark in bookmarks:
        tags = bookmark.get('tags', [])
        new_tags = []
        modified = False
        
        for tag in tags:
            if tag in source_set:
                if target_tag not in new_tags:
                    new_tags.append(target_tag)
                modified = True
            else:
                new_tags.append(tag)
        
        if modified:
            bookmark['tags'] = new_tags
            affected_count += 1
    
    return bookmarks, affected_count


def split_tag(bookmarks: List[Dict], tag: str, new_tags: List[str]) -> Tuple[List[Dict], int]:
    """
    Split a single tag into multiple tags.
    
    Args:
        bookmarks: List of bookmark dictionaries
        tag: Tag to split
        new_tags: List of tags to replace it with
    
    Returns:
        Tuple of (updated bookmarks, number of bookmarks affected)
    """
    affected_count = 0
    
    for bookmark in bookmarks:
        tags = bookmark.get('tags', [])
        if tag in tags:
            # Remove old tag and add new ones
            new_tag_list = [t for t in tags if t != tag]
            new_tag_list.extend([t for t in new_tags if t not in new_tag_list])
            bookmark['tags'] = new_tag_list
            affected_count += 1
    
    return bookmarks, affected_count


def suggest_tags(partial_tag: str, existing_tags: Set[str], separator: str = '/', 
                 max_suggestions: int = 10) -> List[str]:
    """
    Suggest tag completions based on existing tags.
    
    Args:
        partial_tag: Partial tag to complete
        existing_tags: Set of existing tags
        separator: Hierarchy separator
        max_suggestions: Maximum number of suggestions
    
    Returns:
        List of suggested tag completions
    """
    suggestions = []
    
    # Exact prefix matches
    for tag in sorted(existing_tags):
        if tag.startswith(partial_tag) and tag != partial_tag:
            suggestions.append(tag)
            if len(suggestions) >= max_suggestions:
                break
    
    # If not enough suggestions, try fuzzy matching
    if len(suggestions) < max_suggestions:
        partial_lower = partial_tag.lower()
        for tag in sorted(existing_tags):
            if (partial_lower in tag.lower() and 
                tag not in suggestions and 
                tag != partial_tag):
                suggestions.append(tag)
                if len(suggestions) >= max_suggestions:
                    break
    
    return suggestions[:max_suggestions]


def format_tag_tree(tree: Dict, indent: int = 0, separator: str = '/') -> str:
    """
    Format tag tree for display.
    
    Args:
        tree: Tag tree from get_tag_tree()
        indent: Current indentation level
        separator: Hierarchy separator
    
    Returns:
        Formatted string representation of tag tree
    """
    lines = []
    
    for tag, subtree in sorted(tree.items()):
        prefix = "  " * indent
        lines.append(f"{prefix}{tag}")
        
        if subtree:
            lines.append(format_tag_tree(subtree, indent + 1, separator))
    
    return "\n".join(lines)