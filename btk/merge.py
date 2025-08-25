"""
Bookmark merging operations for BTK.

This module provides set operations (union, intersection, difference) for 
bookmark libraries, with both directory-based and list-based APIs.
"""

import logging
import os
import json
from typing import List, Dict, Any
import btk.utils as utils

logging.basicConfig(level=logging.INFO)


# Core merge operations on bookmark lists

def merge_union(bookmark_lists: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Perform set union of multiple bookmark lists.
    
    Args:
        bookmark_lists: List of bookmark lists to merge
        
    Returns:
        Merged bookmark list with duplicates removed (based on unique_id)
    """
    all_bookmarks = {}
    for bookmarks in bookmark_lists:
        for b in bookmarks:
            # Use unique_id as the key to avoid duplicates
            if 'unique_id' in b:
                all_bookmarks[b['unique_id']] = b
    return list(all_bookmarks.values())


def merge_intersection(bookmark_lists: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Perform set intersection of multiple bookmark lists.
    
    Args:
        bookmark_lists: List of bookmark lists to intersect
        
    Returns:
        Bookmarks that appear in all lists (based on unique_id)
    """
    if not bookmark_lists:
        return []
    
    common_unique_ids = None
    bookmark_map = {}
    
    for bookmarks in bookmark_lists:
        unique_ids = set(b['unique_id'] for b in bookmarks if 'unique_id' in b)
        if common_unique_ids is None:
            common_unique_ids = unique_ids
        else:
            common_unique_ids &= unique_ids
        
        # Map unique_id to bookmark
        for b in bookmarks:
            if 'unique_id' in b:
                bookmark_map[b['unique_id']] = b
    
    if common_unique_ids is None:
        return []
    
    return [bookmark_map[uid] for uid in common_unique_ids]


def merge_difference(bookmarks_a: List[Dict[str, Any]], 
                    bookmarks_b: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Perform set difference (A - B).
    
    Args:
        bookmarks_a: First bookmark list
        bookmarks_b: Second bookmark list
        
    Returns:
        Bookmarks in A that are not in B (based on unique_id)
    """
    b_unique_ids = {b['unique_id'] for b in bookmarks_b if 'unique_id' in b}
    return [b for b in bookmarks_a 
            if 'unique_id' in b and b['unique_id'] not in b_unique_ids]


# Directory-based operations (backward compatibility)

def union_libraries(libs, output_dir):
    """Perform set union of multiple bookmark libraries and save to output_dir."""
    # Load bookmarks from each library
    bookmark_lists = []
    for lib in libs:
        bookmarks = utils.load_bookmarks(lib)
        bookmark_lists.append(bookmarks)
    
    # Perform union
    union_bookmarks = merge_union(bookmark_lists)
    
    # Save result
    utils.ensure_dir(output_dir)
    with open(os.path.join(output_dir, 'bookmarks.json'), 'w') as f:
        json.dump(union_bookmarks, f, indent=2)
    logging.info(f"Union of {len(libs)} libraries saved to {output_dir} with {len(union_bookmarks)} bookmarks.")


def intersection_libraries(libs, output_dir):
    """Perform set intersection of multiple bookmark libraries and save to output_dir."""
    if not libs:
        logging.error("No libraries provided for intersection.")
        return
    
    # Load bookmarks from each library
    bookmark_lists = []
    for lib in libs:
        bookmarks = utils.load_bookmarks(lib)
        bookmark_lists.append(bookmarks)
    
    # Perform intersection
    intersection_bookmarks = merge_intersection(bookmark_lists)
    
    # Save result
    utils.ensure_dir(output_dir)
    with open(os.path.join(output_dir, 'bookmarks.json'), 'w') as f:
        json.dump(intersection_bookmarks, f, indent=2)
    logging.info(f"Intersection of {len(libs)} libraries saved to {output_dir} with {len(intersection_bookmarks)} bookmarks.")


def difference_libraries(libs, output_dir):
    """Perform set difference (first library minus others) and save to output_dir."""
    if len(libs) < 2:
        logging.error("Set difference requires at least two libraries.")
        return
    
    # Load bookmarks from first library
    first_bookmarks = utils.load_bookmarks(libs[0])
    
    # Load and merge bookmarks from other libraries
    other_bookmark_lists = []
    for lib in libs[1:]:
        bookmarks = utils.load_bookmarks(lib)
        other_bookmark_lists.append(bookmarks)
    
    # Union all the "other" bookmarks
    other_bookmarks = merge_union(other_bookmark_lists) if other_bookmark_lists else []
    
    # Perform difference
    difference_bookmarks = merge_difference(first_bookmarks, other_bookmarks)
    
    # Save result
    utils.ensure_dir(output_dir)
    with open(os.path.join(output_dir, 'bookmarks.json'), 'w') as f:
        json.dump(difference_bookmarks, f, indent=2)
    logging.info(f"Difference (from {libs[0]} minus others) saved to {output_dir} with {len(difference_bookmarks)} bookmarks.")
