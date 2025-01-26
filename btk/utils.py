import os
import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from tqdm import tqdm
import logging
import hashlib
import shutil
from datetime import datetime, timezone
import jmespath


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Constants
DEFAULT_LIB_DIR = 'bookmarks'
FAVICON_DIR_NAME = 'favicons'
BOOKMARKS_JSON = 'bookmarks.json'

# Ensure default directory structure exists
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def is_bookmark_json(obj):
    """Check if an object is a valid bookmark dictionary."""

    if not isinstance(obj, list):
        return False 
    
    def check_item(item):
        return isinstance(item, dict) and 'id' in item and 'url' in item and \
            'title' in item and 'unique_id' in item and 'visit_count' in item

    return all(check_item(item) for item in obj)

def jmespath_query(bookmarks, query):
    """Apply a JMESPath query to a list of bookmarks."""
    
    if not query:
        return bookmarks
    bookmarks_json = json.loads(json.dumps(bookmarks))
    result = jmespath.search(query, bookmarks_json)
    if is_bookmark_json(result):
        return result, "filter"
    else:
        return result, "transform"

def load_bookmarks(lib_dir):
    """Load bookmarks from a JSON file within the specified library directory."""
    json_file = os.path.join(lib_dir, BOOKMARKS_JSON)
    if not os.path.exists(json_file):
        logging.debug(f"No existing {json_file} found. Starting with an empty bookmark list.")
        return []
    with open(json_file, 'r', encoding='utf-8') as file:
        try:
            bookmarks = json.load(file)
            logging.debug(f"Loaded {len(bookmarks)} bookmarks from {json_file}.")
            return bookmarks
        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON from {json_file}. Starting with an empty list.")
            return []

def save_bookmarks(bookmarks, src_dir, targ_dir):
    """Save bookmarks to a JSON file within the specified library directory."""
    if not bookmarks:
        logging.warning("No bookmarks to save.")
        return
    
    if not targ_dir:
        logging.error("No target directory provided. Cannot save bookmarks.")
        return
    
    #if src_dir is not None and src_dir == targ_dir:
    #    logging.error("Source and target directories are the same. Cannot save bookmarks.")
    #    return
    
    if src_dir is not None and not os.path.exists(src_dir):
        logging.error(f"Source directory '{src_dir}' does not exist. Cannot save bookmarks.")
        return
    
    json_file = os.path.join(targ_dir, BOOKMARKS_JSON)

    # make lib_dir if it doesn't exist
    ensure_dir(targ_dir)

    # iterate over favicons and save them to the favicons directory
    if src_dir is not None and src_dir != targ_dir:
        for b in bookmarks:
            if 'favicon' in b:
                favicon_path = b['favicon']
                b['favicon'] = copy_local_favicon(favicon_path, src_dir, targ_dir)

    # we save the bookmarks to the json file in the lib_dir
    with open(json_file, 'w', encoding='utf-8') as file:
        json.dump(bookmarks, file, ensure_ascii=False, indent=2)

    logging.debug(f"Saved {len(bookmarks)} bookmarks to {json_file}.")

def get_next_id(bookmarks):
    """Get the next unique integer ID for a new bookmark."""
    if not bookmarks:
        return 1
    return max(b['id'] for b in bookmarks) + 1

def generate_unique_id(url, title):
    """Generate a SHA-256 hash as a unique identifier based on URL and title."""
    unique_string = f"{url}{title}"
    hash = hashlib.sha256(unique_string.encode('utf-8')).hexdigest()
    # let's truncate to 8 characters for brevity
    return hash[:8]

def is_remote_url(url):
    """Determine if a URL is remote (http/https) or local."""
    parsed = urlparse(url)
    return parsed.scheme in ('http', 'https')

def generate_unique_filename(url, default_ext='.ico'):
    """Generate a unique filename based on the URL's MD5 hash."""
    hash_object = hashlib.md5(url.encode())
    filename = hash_object.hexdigest()
    parsed = urlparse(url)
    file_ext = os.path.splitext(parsed.path)[1]
    if not file_ext:
        file_ext = default_ext
    return f"{filename}{file_ext}"

def download_favicon(favicon_url, lib_dir):
    """
    Download favicon from the given URL and save it to the specified library's favicons directory.
    Returns the relative path to the saved favicon or None if download fails.
    """
    if not is_remote_url(favicon_url):
        logging.warning(f"Invalid remote favicon URL: {favicon_url}. Skipping download.")
        return None
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; BookmarkTool/1.0)'
        }
        response = requests.get(favicon_url, headers=headers, timeout=5)
        response.raise_for_status()
        filename = generate_unique_filename(favicon_url)
        favicon_dir = os.path.join(lib_dir, FAVICON_DIR_NAME)
        ensure_dir(favicon_dir)
        filepath = os.path.join(favicon_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(response.content)
        relative_path = os.path.relpath(filepath, lib_dir)
        logging.debug(f"Downloaded favicon: {favicon_url} -> {filepath}")
        return relative_path
    except requests.RequestException as e:
        logging.error(f"Failed to download favicon from {favicon_url}: {e}")
        return None

def copy_local_favicon(favicon_path, source_dir, lib_dir):
    """
    Copy a local favicon file to the specified library's favicons directory.
    Returns the relative path to the copied favicon or None if copy fails.
    """
    source_favicon_abs = os.path.abspath(os.path.join(source_dir, favicon_path))
    if not os.path.exists(source_favicon_abs):
        logging.error(f"Local favicon file does not exist: {source_favicon_abs}. Skipping copy.")
        return None
    try:
        filename = generate_unique_filename(favicon_path, default_ext=os.path.splitext(favicon_path)[1] or '.ico')
        favicon_dir = os.path.join(lib_dir, FAVICON_DIR_NAME)
        ensure_dir(favicon_dir)
        destination_path = os.path.join(favicon_dir, filename)
        shutil.copy2(source_favicon_abs, destination_path)
        relative_path = os.path.relpath(destination_path, lib_dir)
        logging.debug(f"Copied local favicon: {source_favicon_abs} -> {destination_path}")
        return relative_path
    except Exception as e:
        logging.error(f"Failed to copy local favicon from {source_favicon_abs}: {e}")
        return None

def parse_date(date_str):
    """
    Parse date string into ISO format.
    Supports multiple date formats.
    """
    date_formats = [
        '%B %d, %Y - %I:%M:%S %p',  # e.g., 'February 24, 2023 - 1:59:56 PM'
        '%B %d, %Y %I:%M:%S %p',   # e.g., 'February 24, 2023 1:59:56 PM'
        # Add additional formats here if needed
    ]
    for fmt in date_formats:
        try:
            date = datetime.strptime(date_str, fmt)
            return date.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    logging.warning(f"Unrecognized date format: '{date_str}'. Using current UTC time.")
    return datetime.now(timezone.utc).isoformat()

def is_valid_url(url):
    """Check if the URL has a valid scheme and netloc."""
    parsed = urlparse(url)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)

def check_url_reachable(url, timeout=10):
    """Check if a URL is reachable."""
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout)
        if response.status_code == 200:
            return True
        else:
            return False
    except requests.RequestException:
        return False

def check_reachable(bookmarks_dir, timeout=10, concurrency=10):
    """Check the reachability of all bookmarks and update their status."""
    bookmarks = load_bookmarks(bookmarks_dir)
    updated = False

    # Prepare a list of bookmarks to check (reachable is None or not)
    to_check = [b for b in bookmarks if b.get('reachable') is None]
    total = len(to_check)
    if total == 0:
        logging.info("All bookmarks have already been checked for reachability.")
        return

    logging.info(f"Checking reachability for {total} bookmarks...")

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_to_bookmark = {executor.submit(check_url_reachable, b['url'], timeout): b for b in to_check}
        
        # Using tqdm for progress bar
        for future in tqdm(as_completed(future_to_bookmark), total=total, desc="Reachability Check"):
            bookmark = future_to_bookmark[future]
            try:
                reachable = future.result()
            except Exception as e:
                logging.error(f"Error checking URL {bookmark['url']}: {e}")
                reachable = False
            bookmark['reachable'] = reachable
            updated = True
            if not reachable:
                logging.warning(f"Bookmark not reachable: {bookmark['url']}")
    
    if updated:
        save_bookmarks(bookmarks, bookmarks_dir, bookmarks_dir)
        logging.info("Reachability status updated successfully.")
    else:
        logging.info("No updates were made to bookmarks.")

def purge_unreachable(bookmarks_dir, confirm=False):
    """Purge all bookmarks marked as not reachable."""
    bookmarks = load_bookmarks(bookmarks_dir)
    unreachable = [b for b in bookmarks if b.get('reachable') == False]
    total_unreachable = len(unreachable)

    if total_unreachable == 0:
        logging.info("No unreachable bookmarks to purge.")
        return

    logging.info(f"Found {total_unreachable} unreachable bookmarks.")

    bookmarks = None
    if confirm:
        new_bookmarks = []
        for b in bookmarks:
            if b.get('reachable') == False:
                resp = input(f"Are you sure you want to purge {b.get('title')}? [y/N]: ")
                if resp.lower() == 'y':
                    logging.debug("Purged bookmark: {b.get('title')}")
                else:
                    new_bookmarks.append(b)
            else:
                new_bookmarks.append(b)
        bookmarks = new_bookmarks
    else:
        bookmarks = [b for b in bookmarks if b.get('reachable') != False]
    
    save_bookmarks(bookmarks, bookmarks_dir, bookmarks_dir)
    logging.info(f"Purged {total_unreachable} unreachable bookmarks successfully.")
