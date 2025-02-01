import os
import logging
import webbrowser
from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from bs4 import BeautifulSoup
import requests
import btk.utils as utils

console = Console()

def import_bookmarks(bookmarks, html_file, lib_dir):
    """Import bookmarks from a Netscape Bookmark Format HTML file into the specified library directory."""
    if not os.path.exists(html_file):
        logging.error(f"HTML file '{html_file}' does not exist.")
        return bookmarks

    with open(html_file, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')

    # Determine the directory of the HTML file to resolve relative favicon paths
    html_dir = os.path.dirname(os.path.abspath(html_file))

    # Iterate over each fieldset (representing a bookmark window/session)
    fieldsets = soup.find_all('fieldset', class_='window')
    logging.info(f"Found {len(fieldsets)} bookmark windows/sessions to import.")

    for fieldset in fieldsets:
        legend = fieldset.find('legend')
        if legend:
            date_str = legend.get_text(strip=True)
            added = utils.parse_date(date_str)
        else:
            logging.warning("No <legend> tag found in fieldset. Using current UTC time.")
            added = datetime.now(timezone.utc).isoformat()

        # Iterate over each bookmark within the fieldset
        for p in fieldset.find_all('p'):
            a_tags = p.find_all('a', href=True)
            img_tag = p.find('img', src=True)
            favicon_url = img_tag['src'] if img_tag else None

            # Handle favicon
            if favicon_url:
                if utils.is_remote_url(favicon_url):
                    favicon_path = utils.download_favicon(favicon_url, lib_dir)
                else:
                    favicon_path = utils.copy_local_favicon(favicon_url, html_dir, lib_dir)
            else:
                favicon_path = None

            if len(a_tags) >= 2:
                # Assuming the second <a> tag contains the actual bookmark
                url = a_tags[1]['href']
                title = a_tags[1].get_text(strip=True)

                # Check for duplicates based on unique_id
                unique_id = utils.generate_unique_id(url, title)
                if any(b['unique_id'] == unique_id for b in bookmarks):
                    logging.info(f"Duplicate bookmark found for URL '{url}' and Title '{title}'. Skipping.")
                    continue

                # Assign a unique ID
                bookmark_id = utils.get_next_id(bookmarks)

                # Create bookmark entry with default values
                bookmark = {
                    'id': bookmark_id,
                    'unique_id': unique_id,
                    'title': title,
                    'url': url,
                    'added': added,
                    'stars': False,
                    'tags': [],
                    'visit_count': 0,
                    'description': "",
                    'favicon': favicon_path,
                    'last_visited': None,
                    'reachable': None
                }

                bookmarks.append(bookmark)
                logging.info(f"Imported bookmark: ID {bookmark_id} - '{title}' - {url}")
            else:
                logging.warning("Insufficient <a> tags found in <p>. Skipping this entry.")

    logging.info(f"Import complete. Total bookmarks: {len(bookmarks)}")
    return bookmarks

def search_bookmarks(bookmarks, query):
    """Search bookmarks by title or URL containing the query (case-insensitive)."""
    results = [b for b in bookmarks if query.lower() in b['title'].lower() or query.lower() in b['url'].lower()]
    logging.info(f"Found {len(results)} bookmarks matching query '{query}'.")
    return results

def add_bookmark(bookmarks, title, url, stars=False, tags=None, description="", lib_dir=None):
    """Add a new bookmark with optional stars, tags, and description."""
    unique_id = utils.generate_unique_id(url, title)
    if any(b['unique_id'] == unique_id for b in bookmarks):
        logging.error(f"A bookmark with URL '{url}' and Title '{title}' already exists.")
        return bookmarks

    if tags is None:
        tags = []

    bookmark_id = utils.get_next_id(bookmarks)

    bookmark = {
        'id': bookmark_id,
        'unique_id': unique_id,
        'title': title,
        'url': url,
        'added': datetime.now(timezone.utc).isoformat(),
        'stars': stars,
        'tags': tags,
        'visit_count': 0,
        'description': description,
        'favicon': None,  # Optional: Can be set manually later
        'last_visited': None,
        'reachable': None
    }

    bookmarks.append(bookmark)
    logging.info(f"Added new bookmark: ID {bookmark_id} - '{title}' - {url}")
    return bookmarks

def remove_bookmark(bookmarks, bookmark_id):
    """Remove a bookmark by its ID."""
    initial_count = len(bookmarks)
    bookmarks = [b for b in bookmarks if b['id'] != bookmark_id]
    final_count = len(bookmarks)
    if final_count < initial_count:
        logging.info(f"Removed bookmark with ID {bookmark_id}.")
    else:
        logging.warning(f"No bookmark found with ID {bookmark_id}.")
    return bookmarks

def list_bookmarks(bookmarks, indices=None):
    """List all bookmarks with their IDs and unique IDs."""
    if not bookmarks:
        console.print(f"[red]No bookmarks available.[/red]")
        return
    table = Table(title="List of Bookmarks", show_header=True, header_style="bold magenta")
    if indices is not None:
        table.add_column("#", style="dim", justify="right")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Title", style="bold")
    table.add_column("Tags", style="yellow")
    table.add_column("Star", style="#FFD700")
    table.add_column("Visits", style="magenta")
    table.add_column("Added", style="dim")
    table.add_column("Last Visit", style="dim")
    table.add_column("Desc", style="italic")

    for i, b in enumerate(bookmarks):
        stars = "⭐" if b.get('stars') else ""
        tags = ", ".join(b.get('tags', []))
        last_visited = b.get('last_visited') or "-"
        if b.get('reachable'):
            title = f"[link={b['url']}]🔗 {b['title']}[/link]"
        else:
            title = f"[link={b['url']}]❌ {b['title']}[/link]"
        table.add_row(
            str(indices[i]) if indices is not None else str(i),
            str(b['id']),
            title,
            tags,
            stars,
            str(b.get('visit_count', 0)),
            b['added'].split("T")[0],
            last_visited.split("T")[0], 
            b.get('description', ""),
        )
    
    console.print(table)

def visit_bookmark(bookmarks, bookmark_id, method='browser', lib_dir=None):
    """
    Visit a bookmark either through the browser or console.
    - method: 'browser' or 'console'
    """
    for bookmark in bookmarks:
        if bookmark['id'] == bookmark_id:
            if method == 'browser':
                try:
                    webbrowser.open(bookmark['url'])
                    logging.info(f"Opened '{bookmark['title']}' in the default browser.")
                except Exception as e:
                    logging.error(f"Failed to open URL '{bookmark['url']}' in browser: {e}")
            elif method == 'console':
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (compatible; BookmarkTool/1.0)'
                    }
                    response = requests.get(bookmark['url'], headers=headers, timeout=10)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'html.parser')
                    text = soup.get_text(separator='\n')
                    # Use rich to display content
                    content = Text(text[:1000] + "...", style="dim")
                    panel = Panel.fit(
                        content,
                        title=bookmark['title'],
                        subtitle=bookmark['url'],
                        border_style="green"
                    )
                    console.print(panel)
                except requests.RequestException as e:
                    logging.error(f"Failed to retrieve content from '{bookmark['url']}': {e}")
                except Exception as e:
                    logging.error(f"Error processing content from '{bookmark['url']}': {e}")
            else:
                logging.error(f"Unknown visit method '{method}'.")
                return bookmarks
            # Increment visit_count and update last_visited
            bookmark['visit_count'] += 1
            bookmark['last_visited'] = datetime.now(timezone.utc).isoformat()
            logging.info(f"Updated visit_count for '{bookmark['title']}' to {bookmark['visit_count']}.")
            return bookmarks
    logging.warning(f"No bookmark found with ID {bookmark_id}.")
    return bookmarks
