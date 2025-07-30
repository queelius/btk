import logging
import os
import json
import btk.utils as utils

logging.basicConfig(level=logging.INFO)

def union_libraries(libs, output_dir):
    """Perform set union of multiple bookmark libraries and save to output_dir."""
    all_bookmarks = {}
    for lib in libs:
        bookmarks = utils.load_bookmarks(lib)
        for b in bookmarks:
            all_bookmarks[b['unique_id']] = b
    union_bookmarks = list(all_bookmarks.values())
    utils.ensure_dir(output_dir)
    with open(os.path.join(output_dir, 'bookmarks.json'), 'w') as f:
        import json
        json.dump(union_bookmarks, f, indent=2)
    logging.info(f"Union of {len(libs)} libraries saved to {output_dir} with {len(union_bookmarks)} bookmarks.")

def intersection_libraries(libs, output_dir):
    """Perform set intersection of multiple bookmark libraries and save to output_dir."""
    if not libs:
        logging.error("No libraries provided for intersection.")
        return
    common_unique_ids = None
    bookmark_map = {}
    for lib in libs:
        bookmarks = utils.load_bookmarks(lib)
        unique_ids = set(b['unique_id'] for b in bookmarks)
        if common_unique_ids is None:
            common_unique_ids = unique_ids
        else:
            common_unique_ids &= unique_ids
        # Map unique_id to bookmark (assuming same unique_id implies same bookmark)
        for b in bookmarks:
            bookmark_map[b['unique_id']] = b
    intersection_bookmarks = [bookmark_map[uid] for uid in common_unique_ids]
    utils.ensure_dir(output_dir)
    with open(os.path.join(output_dir, 'bookmarks.json'), 'w') as f:
        import json
        json.dump(intersection_bookmarks, f, indent=2)
    logging.info(f"Intersection of {len(libs)} libraries saved to {output_dir} with {len(intersection_bookmarks)} bookmarks.")

def difference_libraries(libs, output_dir):
    """Perform set difference (first library minus others) and save to output_dir."""
    if len(libs) < 2:
        logging.error("Set difference requires at least two libraries.")
        return
    first_lib = libs[0]
    other_libs = libs[1:]
    first_bookmarks = utils.load_bookmarks(first_lib)
    other_unique_ids = set()
    for lib in other_libs:
        bookmarks = utils.load_bookmarks(lib)
        other_unique_ids.update(b['unique_id'] for b in bookmarks)
    difference_bookmarks = [b for b in first_bookmarks if b['unique_id'] not in other_unique_ids]
    utils.ensure_dir(output_dir)
    with open(os.path.join(output_dir, 'bookmarks.json'), 'w') as f:
        import json
        json.dump(difference_bookmarks, f, indent=2)
    logging.info(f"Difference (from {first_lib} minus others) saved to {output_dir} with {len(difference_bookmarks)} bookmarks.")
