import os
import logging
import webbrowser
from datetime import datetime, timezone
import csv
import io
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from bs4 import BeautifulSoup
import re
import requests
from colorama import init as colorama_init, Fore, Style
import btk.utils as utils
from btk.progress import with_progress, spinner

# Initialize colorama and rich console
colorama_init(autoreset=True)
console = Console()


def import_bookmarks(html_file, bookmarks, lib_dir, format='netscape'):
    """Import bookmarks from an HTML file in Netscape Bookmark Format."""
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
    except Exception as e:
        logging.error(f"Failed to read HTML file '{html_file}': {e}")
        return bookmarks

    new_bookmarks = []

    # Check if it's a Netscape bookmark file
    if 'netscape' in str(soup).lower() or format == 'netscape':
        # Parse Netscape bookmark format
        for a_tag in soup.find_all('a'):
            url = a_tag.get('href')
            if not url:
                continue

            title = a_tag.get_text(strip=True) or 'Untitled'
            tags = a_tag.get('tags', '').split(',') if a_tag.get('tags') else []
            description = ''
            
            # Look for description in the next DD tag
            next_sibling = a_tag.find_next_sibling()
            if next_sibling and next_sibling.name == 'dd':
                description = next_sibling.get_text(strip=True)

            # Check for duplicates
            duplicate = False
            for existing_bookmark in bookmarks:
                if existing_bookmark['url'] == url:
                    logging.info(f"Skipping duplicate bookmark: {title} ({url})")
                    duplicate = True
                    break

            if not duplicate:
                new_bookmarks.append({
                    'title': title,
                    'url': url,
                    'tags': tags,
                    'description': description
                })
    else:
        # Original parsing logic for other HTML files
        for a_tag in soup.find_all('a', href=True):
            url = a_tag['href']
            title = a_tag.get_text(strip=True) or url
            tags = []
            description = ''

            # Try to extract tags from the parent or surrounding elements
            parent = a_tag.parent
            if parent:
                parent_text = parent.get_text()
                # Simple heuristic: look for tags in the parent text
                tag_match = re.search(r'tags?:\s*([^,\n]+(?:,\s*[^,\n]+)*)', parent_text, re.IGNORECASE)
                if tag_match:
                    tags = [tag.strip() for tag in tag_match.group(1).split(',')]

            # Check for duplicates
            duplicate = False
            for existing_bookmark in bookmarks:
                if existing_bookmark['url'] == url:
                    logging.info(f"Skipping duplicate bookmark: {title} ({url})")
                    duplicate = True
                    break

            if not duplicate:
                new_bookmarks.append({
                    'title': title,
                    'url': url,
                    'tags': tags,
                    'description': description
                })

    # Add new bookmarks
    for bookmark_data in new_bookmarks:
        bookmarks = add_bookmark(
            bookmarks,
            title=bookmark_data['title'],
            url=bookmark_data['url'],
            tags=bookmark_data['tags'],
            description=bookmark_data['description'],
            lib_dir=lib_dir,
            stars=False
        )

    logging.info(f"Imported {len(new_bookmarks)} new bookmarks from '{html_file}'.")
    return bookmarks


def search_bookmarks(bookmarks, query):
    """Search for bookmarks by query (case-insensitive) in title, URL, description, and tags."""
    query_lower = query.lower()
    results = []

    for bookmark in bookmarks:
        # Search in title
        if query_lower in bookmark.get('title', '').lower():
            results.append(bookmark)
        # Search in URL
        elif query_lower in bookmark.get('url', '').lower():
            results.append(bookmark)
        # Search in description
        elif query_lower in bookmark.get('description', '').lower():
            results.append(bookmark)
        # Search in tags
        elif any(query_lower in tag.lower() for tag in bookmark.get('tags', [])):
            results.append(bookmark)

    logging.info(f"Found {len(results)} bookmarks matching '{query}'.")
    return results


def add_bookmark(bookmarks, title, url, stars, tags, description, lib_dir):
    """Add a new bookmark to the library."""
    # Validate URL
    if not utils.is_valid_url(url):
        logging.error(f"Invalid URL: {url}")
        return bookmarks

    # Check for duplicates
    for bookmark in bookmarks:
        if bookmark['url'] == url:
            logging.warning(f"Bookmark with URL '{url}' already exists.")
            return bookmarks

    # Generate new ID
    new_id = utils.get_next_id(bookmarks)

    # Create new bookmark
    bookmark_title = title or 'Untitled'
    new_bookmark = {
        'id': new_id,
        'unique_id': utils.generate_unique_id(url, bookmark_title),
        'title': bookmark_title,
        'url': url,
        'added': datetime.now(timezone.utc).isoformat(),
        'stars': stars,
        'tags': tags,
        'visit_count': 0,
        'description': description,
        'favicon': None,
        'last_visited': None,
        'reachable': None
    }

    # Try to download favicon
    try:
        favicon_filename = utils.download_favicon(url, lib_dir)
        if favicon_filename:
            new_bookmark['favicon'] = favicon_filename
    except Exception as e:
        logging.warning(f"Failed to download favicon for '{url}': {e}")

    bookmarks.append(new_bookmark)
    logging.info(f"Added bookmark: {title} ({url})")
    console.print(f"[green]✓ Added bookmark: {title}[/green]")
    return bookmarks


def remove_bookmark(bookmarks, bookmark_id):
    """Remove a bookmark by ID."""
    for i, bookmark in enumerate(bookmarks):
        if bookmark['id'] == bookmark_id:
            removed = bookmarks.pop(i)
            logging.info(f"Removed bookmark: {removed['title']} ({removed['url']})")
            console.print(f"[red]✗ Removed bookmark: {removed['title']}[/red]")
            return bookmarks
    
    logging.warning(f"No bookmark found with ID {bookmark_id}.")
    console.print(f"[yellow]⚠ No bookmark found with ID {bookmark_id}[/yellow]")
    return bookmarks


def list_bookmarks(bookmarks, indices=None):
    """List all bookmarks with their IDs and unique IDs."""
    if not bookmarks:
        console.print(f"[red]No bookmarks available.[/red]")
        return []
    
    # Filter bookmarks by indices if provided
    if indices is not None:
        filtered_bookmarks = []
        for idx in indices:
            bookmark = next((b for b in bookmarks if b['id'] == idx), None)
            if bookmark:
                filtered_bookmarks.append(bookmark)
        bookmarks_to_display = filtered_bookmarks
    else:
        bookmarks_to_display = bookmarks
    
    if not bookmarks_to_display:
        console.print(f"[yellow]No bookmarks found with the specified indices.[/yellow]")
        return []
    
    # Create a table
    table = Table(title="List of Bookmarks", show_header=True, header_style="bold magenta")
    table.add_column("#", style="cyan", no_wrap=True)
    table.add_column("ID", style="green")
    table.add_column("Title", style="blue")
    table.add_column("Tags", style="yellow")
    table.add_column("Star", style="red")
    table.add_column("Visits", style="magenta")
    table.add_column("Added", style="green")
    table.add_column("Last Visit", style="cyan")
    table.add_column("Desc", style="white")
    
    # Add rows
    for idx, bookmark in enumerate(bookmarks_to_display):
        tags_str = ', '.join(bookmark.get('tags', []))
        star_str = '⭐' if bookmark.get('stars', False) else ''
        visits_str = str(bookmark.get('visit_count', 0))
        added_date = bookmark.get('added', 'Unknown')
        if added_date != 'Unknown':
            try:
                added_date = datetime.fromisoformat(added_date.replace('Z', '+00:00')).strftime('%Y-%m-%d')
            except:
                pass
        last_visit = bookmark.get('last_visited', '-')
        if last_visit != '-':
            try:
                last_visit = datetime.fromisoformat(last_visit.replace('Z', '+00:00')).strftime('%Y-%m-%d')
            except:
                last_visit = '-'
        
        description = bookmark.get('description', '')
        if len(description) > 30:
            description = description[:27] + '...'
        
        # Add reachability indicator
        reachable_indicator = ''
        if 'reachable' in bookmark:
            reachable_indicator = '✅ ' if bookmark['reachable'] else '❌ '
        
        table.add_row(
            str(idx),
            str(bookmark['id']),
            reachable_indicator + bookmark.get('title', 'Untitled'),
            tags_str,
            star_str,
            visits_str,
            added_date,
            last_visit,
            description
        )
    
    console.print(table)
    
    # Show URLs in a separate section
    console.print("\n[bold]URLs:[/bold]")
    for idx, bookmark in enumerate(bookmarks_to_display):
        console.print(f"  [{idx}] {bookmark['url']}")
    
    return bookmarks_to_display


def visit_bookmark(bookmarks, bookmark_id, method='browser', lib_dir=None):
    """Visit a bookmark by ID using the specified method."""
    for bookmark in bookmarks:
        if bookmark['id'] == bookmark_id:
            url = bookmark['url']
            if method == 'browser':
                try:
                    webbrowser.open(url)
                    logging.info(f"Opened '{bookmark['title']}' in browser.")
                    console.print(f"[green]✓ Opened '{bookmark['title']}' in browser[/green]")
                except Exception as e:
                    logging.error(f"Failed to open '{url}' in browser: {e}")
                    console.print(f"[red]✗ Failed to open '{url}' in browser[/red]")
                    return bookmarks
            elif method == 'console':
                # Fetch and display content in console
                try:
                    response = requests.get(url, timeout=10)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Extract text content
                    text = soup.get_text(separator='\n', strip=True)
                    
                    # Limit the output
                    lines = text.split('\n')
                    content = '\n'.join(lines[:50])  # Show first 50 lines
                    if len(lines) > 50:
                        content += f"\n\n... (Showing first 50 lines of {len(lines)} total)"
                    
                    # Display in a panel
                    panel = Panel(
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


def export_bookmarks_html(bookmarks, output_path):
    """Export bookmarks to Netscape HTML format (compatible with browsers)."""
    html_content = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<!-- This is an automatically generated file.
     It will be read and overwritten.
     DO NOT EDIT! -->
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
"""
    
    for bookmark in bookmarks:
        # Convert timestamp to Unix time
        added_timestamp = bookmark.get('added', datetime.now().isoformat())
        if isinstance(added_timestamp, str):
            try:
                dt = datetime.fromisoformat(added_timestamp.replace('Z', '+00:00'))
                unix_time = int(dt.timestamp())
            except:
                unix_time = int(datetime.now().timestamp())
        else:
            unix_time = int(datetime.now().timestamp())
        
        # Build bookmark entry
        tags = ','.join(bookmark.get('tags', []))
        title = bookmark.get('title', 'Untitled')
        url = bookmark['url']
        
        html_content += f'    <DT><A HREF="{url}" ADD_DATE="{unix_time}"'
        if tags:
            html_content += f' TAGS="{tags}"'
        html_content += f'>{title}</A>\n'
        
        # Add description if present
        description = bookmark.get('description', '')
        if description:
            html_content += f'    <DD>{description}\n'
    
    html_content += """</DL><p>
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    console.print(f"[green]Bookmarks exported to {output_path}[/green]")


def export_bookmarks_csv(bookmarks, output_path):
    """Export bookmarks to CSV format."""
    if not bookmarks:
        console.print("[yellow]No bookmarks to export[/yellow]")
        return
    
    # Get all unique fields from bookmarks
    all_fields = set()
    for bookmark in bookmarks:
        all_fields.update(bookmark.keys())
    
    # Define field order (common fields first)
    field_order = ['id', 'title', 'url', 'tags', 'description', 'stars', 'added', 'visit_count', 'last_visited']
    other_fields = sorted(all_fields - set(field_order))
    fieldnames = field_order + other_fields
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for bookmark in bookmarks:
            # Convert tags list to comma-separated string
            row = bookmark.copy()
            if 'tags' in row and isinstance(row['tags'], list):
                row['tags'] = ','.join(row['tags'])
            writer.writerow(row)
    
    console.print(f"[green]Bookmarks exported to {output_path}[/green]")


def import_bookmarks_markdown(markdown_file, bookmarks, lib_dir):
    """Import links from a markdown file.
    
    Extracts all links in the following formats:
    - [Title](url)
    - <url>
    - Raw URLs starting with http:// or https://
    """
    try:
        with open(markdown_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        logging.error(f"Failed to read markdown file '{markdown_file}': {e}")
        return bookmarks
    
    new_bookmarks = []
    
    # Regex patterns for different link formats
    # Pattern 1: [title](url)
    markdown_link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    
    # Pattern 2: <url>
    angle_bracket_pattern = re.compile(r'<(https?://[^>]+)>')
    
    # Pattern 3: Raw URLs (stop at common punctuation that typically ends URLs)
    raw_url_pattern = re.compile(r'(?<!["\'\(])https?://[^\s<>"{}|\\^`\[\]()]+(?<![.,;:!?])')
    
    # Track URLs we've already seen to avoid duplicates
    seen_urls = set()
    
    # Extract markdown links with titles
    for match in markdown_link_pattern.finditer(content):
        title = match.group(1).strip()
        url = match.group(2).strip()
        seen_urls.add(url)  # Mark this URL as seen
        
        # Skip if already exists
        if any(b['url'] == url for b in bookmarks):
            continue
            
        new_bookmarks.append({
            'title': title,
            'url': url,
            'tags': ['markdown-import'],
            'description': ''
        })
    
    # Extract angle bracket URLs
    for match in angle_bracket_pattern.finditer(content):
        url = match.group(1).strip()
        seen_urls.add(url)  # Mark this URL as seen
        
        # Skip if already processed or exists
        if any(b['url'] == url for b in new_bookmarks) or any(b['url'] == url for b in bookmarks):
            continue
            
        new_bookmarks.append({
            'title': url,  # Use URL as title
            'url': url,
            'tags': ['markdown-import'],
            'description': ''
        })
    
    # Extract raw URLs (but skip those already found in markdown links or angle brackets)
    for match in raw_url_pattern.finditer(content):
        url = match.group(0).strip()
        
        # Skip if we've already seen this URL in a markdown link or angle brackets
        if url in seen_urls:
            continue
            
        # Skip if already processed or exists
        if any(b['url'] == url for b in new_bookmarks) or any(b['url'] == url for b in bookmarks):
            continue
            
        new_bookmarks.append({
            'title': url,  # Use URL as title
            'url': url,
            'tags': ['markdown-import'],
            'description': ''
        })
    
    # Add new bookmarks
    for bookmark_data in new_bookmarks:
        bookmarks = add_bookmark(
            bookmarks,
            title=bookmark_data['title'],
            url=bookmark_data['url'],
            tags=bookmark_data['tags'],
            description=bookmark_data['description'],
            lib_dir=lib_dir,
            stars=False
        )
    
    logging.info(f"Imported {len(new_bookmarks)} new bookmarks from '{markdown_file}'.")
    console.print(f"[green]✓ Imported {len(new_bookmarks)} bookmarks from markdown file[/green]")
    return bookmarks


def export_bookmarks_json(bookmarks, output_path):
    """Export bookmarks to JSON format."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(bookmarks, f, indent=2, ensure_ascii=False)
    
    console.print(f"[green]Bookmarks exported to {output_path}[/green]")


def export_bookmarks_markdown(bookmarks, output_path):
    """Export bookmarks to Markdown format."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Bookmarks\n\n")
        
        # Group bookmarks by tags for better organization
        bookmarks_by_tag = {}
        untagged = []
        
        for bookmark in bookmarks:
            tags = bookmark.get('tags', [])
            if not tags:
                untagged.append(bookmark)
            else:
                for tag in tags:
                    if tag not in bookmarks_by_tag:
                        bookmarks_by_tag[tag] = []
                    bookmarks_by_tag[tag].append(bookmark)
        
        # Write bookmarks grouped by tag
        for tag, tagged_bookmarks in sorted(bookmarks_by_tag.items()):
            f.write(f"## {tag}\n\n")
            for bookmark in tagged_bookmarks:
                title = bookmark.get('title', 'Untitled')
                url = bookmark['url']
                description = bookmark.get('description', '')
                stars = '⭐ ' if bookmark.get('stars', False) else ''
                
                f.write(f"- {stars}[{title}]({url})")
                if description:
                    f.write(f" - {description}")
                f.write("\n")
            f.write("\n")
        
        # Write untagged bookmarks
        if untagged:
            f.write("## Untagged\n\n")
            for bookmark in untagged:
                title = bookmark.get('title', 'Untitled')
                url = bookmark['url']
                description = bookmark.get('description', '')
                stars = '⭐ ' if bookmark.get('stars', False) else ''
                
                f.write(f"- {stars}[{title}]({url})")
                if description:
                    f.write(f" - {description}")
                f.write("\n")
    
    console.print(f"[green]Bookmarks exported to {output_path}[/green]")


def export_bookmarks_hierarchical(bookmarks, output_dir, format='markdown', separator='/'):
    """Export bookmarks to a hierarchical structure based on tags.
    
    Args:
        bookmarks: List of bookmarks to export
        output_dir: Directory to export to
        format: Export format for each file ('markdown', 'html', 'json')
        separator: Tag hierarchy separator (default: '/')
    """
    from collections import defaultdict
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Group bookmarks by tag hierarchy
    tag_tree = defaultdict(list)
    untagged_bookmarks = []
    
    for bookmark in bookmarks:
        tags = bookmark.get('tags', [])
        if not tags:
            untagged_bookmarks.append(bookmark)
        else:
            for tag in tags:
                tag_tree[tag].append(bookmark)
    
    # Process tag hierarchy
    tag_groups = defaultdict(lambda: defaultdict(list))
    
    for tag, tagged_bookmarks in tag_tree.items():
        parts = tag.split(separator)
        if len(parts) > 1:
            # Hierarchical tag
            category = parts[0]
            subtag = separator.join(parts[1:])
            tag_groups[category][subtag].extend(tagged_bookmarks)
        else:
            # Simple tag
            tag_groups[tag][''].extend(tagged_bookmarks)
    
    # Export each category
    exported_files = []
    
    for category, subtags in tag_groups.items():
        # Create category directory
        category_dir = output_path / category
        category_dir.mkdir(exist_ok=True)
        
        # Export bookmarks for this category
        if format == 'markdown':
            # Create a markdown file for the category
            category_file = category_dir / f"{category}.md"
            with open(category_file, 'w', encoding='utf-8') as f:
                f.write(f"# {category.title()} Bookmarks\n\n")
                
                # Process subtags
                for subtag, subtag_bookmarks in sorted(subtags.items()):
                    if subtag:
                        f.write(f"## {subtag.replace(separator, ' > ')}\n\n")
                    
                    # Remove duplicates
                    seen_urls = set()
                    unique_bookmarks = []
                    for b in subtag_bookmarks:
                        if b['url'] not in seen_urls:
                            seen_urls.add(b['url'])
                            unique_bookmarks.append(b)
                    
                    # Write bookmarks
                    for bookmark in sorted(unique_bookmarks, key=lambda x: x.get('title', '')):
                        title = bookmark.get('title', 'Untitled')
                        url = bookmark['url']
                        description = bookmark.get('description', '')
                        stars = '⭐ ' if bookmark.get('stars', False) else ''
                        
                        f.write(f"- {stars}[{title}]({url})")
                        if description:
                            f.write(f" - {description}")
                        f.write("\n")
                    f.write("\n")
            
            exported_files.append(str(category_file))
            
        elif format == 'json':
            # Export as JSON files per category
            category_file = category_dir / f"{category}.json"
            category_bookmarks = []
            
            for subtag, subtag_bookmarks in subtags.items():
                # Add subtag info to bookmarks
                for bookmark in subtag_bookmarks:
                    bookmark_copy = bookmark.copy()
                    bookmark_copy['category'] = category
                    if subtag:
                        bookmark_copy['subcategory'] = subtag
                    category_bookmarks.append(bookmark_copy)
            
            with open(category_file, 'w', encoding='utf-8') as f:
                json.dump(category_bookmarks, f, indent=2, ensure_ascii=False)
            
            exported_files.append(str(category_file))
            
        elif format == 'html':
            # Export as HTML files per category
            category_file = category_dir / f"{category}.html"
            html_bookmarks = []
            
            for subtag, subtag_bookmarks in subtags.items():
                html_bookmarks.extend(subtag_bookmarks)
            
            # Remove duplicates
            seen_urls = set()
            unique_bookmarks = []
            for b in html_bookmarks:
                if b['url'] not in seen_urls:
                    seen_urls.add(b['url'])
                    unique_bookmarks.append(b)
            
            export_bookmarks_html(unique_bookmarks, str(category_file))
            exported_files.append(str(category_file))
    
    # Handle untagged bookmarks
    if untagged_bookmarks:
        if format == 'markdown':
            untagged_file = output_path / 'untagged.md'
            with open(untagged_file, 'w', encoding='utf-8') as f:
                f.write("# Untagged Bookmarks\n\n")
                for bookmark in sorted(untagged_bookmarks, key=lambda x: x.get('title', '')):
                    title = bookmark.get('title', 'Untitled')
                    url = bookmark['url']
                    description = bookmark.get('description', '')
                    stars = '⭐ ' if bookmark.get('stars', False) else ''
                    
                    f.write(f"- {stars}[{title}]({url})")
                    if description:
                        f.write(f" - {description}")
                    f.write("\n")
            exported_files.append(str(untagged_file))
        elif format == 'json':
            untagged_file = output_path / 'untagged.json'
            with open(untagged_file, 'w', encoding='utf-8') as f:
                json.dump(untagged_bookmarks, f, indent=2, ensure_ascii=False)
            exported_files.append(str(untagged_file))
        elif format == 'html':
            untagged_file = output_path / 'untagged.html'
            export_bookmarks_html(untagged_bookmarks, str(untagged_file))
            exported_files.append(str(untagged_file))
    
    # Create index file
    index_file = output_path / 'index.md'
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write("# Bookmark Export Index\n\n")
        f.write(f"Exported {len(bookmarks)} bookmarks organized by tags.\n\n")
        f.write("## Categories\n\n")
        
        for category in sorted(tag_groups.keys()):
            f.write(f"- [{category.title()}](./{category}/{category}.md)\n")
        
        if untagged_bookmarks:
            f.write("- [Untagged](./untagged.md)\n")
    
    console.print(f"[green]Bookmarks exported hierarchically to {output_path}[/green]")
    console.print(f"Created {len(exported_files)} files organized by tags")
    
    return exported_files


def import_bookmarks_json(json_file, bookmarks, lib_dir):
    """Import bookmarks from a JSON file."""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            imported_data = json.load(f)
    except Exception as e:
        logging.error(f"Failed to read JSON file '{json_file}': {e}")
        return bookmarks
    
    # Ensure we have a list
    if not isinstance(imported_data, list):
        logging.error(f"JSON file must contain a list of bookmarks")
        return bookmarks
    
    new_bookmarks = []
    
    for item in imported_data:
        if not isinstance(item, dict):
            continue
            
        # Extract fields
        url = item.get('url', '')
        if not url:
            continue
            
        title = item.get('title', url)
        tags = item.get('tags', [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',')]
        description = item.get('description', '')
        stars = item.get('stars', False)
        
        # Check for duplicates
        if any(b['url'] == url for b in bookmarks):
            logging.info(f"Skipping duplicate bookmark: {title} ({url})")
            continue
            
        new_bookmarks.append({
            'title': title,
            'url': url,
            'tags': tags,
            'description': description,
            'stars': stars
        })
    
    # Add new bookmarks
    for bookmark_data in new_bookmarks:
        bookmarks = add_bookmark(
            bookmarks,
            title=bookmark_data['title'],
            url=bookmark_data['url'],
            tags=bookmark_data['tags'],
            description=bookmark_data['description'],
            lib_dir=lib_dir,
            stars=bookmark_data['stars']
        )
    
    logging.info(f"Imported {len(new_bookmarks)} new bookmarks from '{json_file}'.")
    console.print(f"[green]✓ Imported {len(new_bookmarks)} bookmarks from JSON file[/green]")
    return bookmarks


def import_bookmarks_csv(csv_file, bookmarks, lib_dir, fields):
    """Import bookmarks from a CSV file."""
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            imported_data = list(reader)
    except Exception as e:
        logging.error(f"Failed to read CSV file '{csv_file}': {e}")
        return bookmarks
    
    new_bookmarks = []
    
    for row in imported_data:
        # Extract fields based on field names
        url = row.get('url', '')
        if not url:
            continue
            
        title = row.get('title', url)
        tags = row.get('tags', '')
        if tags:
            tags = [t.strip() for t in tags.split(',')]
        else:
            tags = []
        description = row.get('description', '')
        stars = row.get('stars', '').lower() in ['true', '1', 'yes']
        
        # Check for duplicates
        if any(b['url'] == url for b in bookmarks):
            logging.info(f"Skipping duplicate bookmark: {title} ({url})")
            continue
            
        new_bookmarks.append({
            'title': title,
            'url': url,
            'tags': tags,
            'description': description,
            'stars': stars
        })
    
    # Add new bookmarks
    for bookmark_data in new_bookmarks:
        bookmarks = add_bookmark(
            bookmarks,
            title=bookmark_data['title'],
            url=bookmark_data['url'],
            tags=bookmark_data['tags'],
            description=bookmark_data['description'],
            lib_dir=lib_dir,
            stars=bookmark_data['stars']
        )
    
    logging.info(f"Imported {len(new_bookmarks)} new bookmarks from '{csv_file}'.")
    console.print(f"[green]✓ Imported {len(new_bookmarks)} bookmarks from CSV file[/green]")
    return bookmarks


def import_bookmarks_html_generic(html_file, bookmarks, lib_dir):
    """Import bookmarks from a generic HTML file.
    
    Extracts all <a> tags with href attributes from any HTML file,
    not just Netscape bookmark format.
    """
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
    except Exception as e:
        logging.error(f"Failed to read HTML file '{html_file}': {e}")
        return bookmarks
    
    new_bookmarks = []
    
    # Find all anchor tags with href
    for a_tag in soup.find_all('a', href=True):
        url = a_tag.get('href', '').strip()
        
        # Skip empty URLs or anchors
        if not url or url.startswith('#'):
            continue
            
        # Handle protocol-relative URLs
        if url.startswith('//'):
            url = 'https:' + url
        
        # Skip non-HTTP(S) URLs
        if not url.startswith(('http://', 'https://')):
            continue
        
        # Get title from link text or use URL
        title = a_tag.get_text(strip=True) or url
        
        # Try to extract additional metadata
        tags = []
        description = ''
        
        # Look for title attribute
        title_attr = a_tag.get('title', '')
        if title_attr and not description:
            description = title_attr
        
        # Look for rel attribute for tags
        rel = a_tag.get('rel', [])
        if isinstance(rel, list):
            tags.extend(rel)
        elif isinstance(rel, str):
            tags.extend(rel.split())
        
        # Look for class names that might indicate categories
        classes = a_tag.get('class', [])
        if classes:
            # Add meaningful class names as tags
            for cls in classes:
                if cls and not cls.startswith(('btn', 'link', 'nav')):
                    tags.append(cls)
        
        # Check for duplicates
        if any(b['url'] == url for b in bookmarks):
            logging.info(f"Skipping duplicate bookmark: {title} ({url})")
            continue
            
        if any(b['url'] == url for b in new_bookmarks):
            continue
            
        new_bookmarks.append({
            'title': title,
            'url': url,
            'tags': list(set(tags + ['html-import'])),  # Remove duplicates and add import tag
            'description': description
        })
    
    # Add new bookmarks
    for bookmark_data in new_bookmarks:
        bookmarks = add_bookmark(
            bookmarks,
            title=bookmark_data['title'],
            url=bookmark_data['url'],
            tags=bookmark_data['tags'],
            description=bookmark_data['description'],
            lib_dir=lib_dir,
            stars=False
        )
    
    logging.info(f"Imported {len(new_bookmarks)} new bookmarks from '{html_file}'.")
    console.print(f"[green]✓ Imported {len(new_bookmarks)} bookmarks from HTML file[/green]")
    return bookmarks


@with_progress("Scanning directory for bookmarks")
def import_bookmarks_directory(directory, bookmarks, lib_dir, recursive=True, formats=None):
    """Import bookmarks from all supported files in a directory.
    
    Args:
        directory: Directory to scan for files
        bookmarks: Existing bookmarks list
        lib_dir: Library directory for storing bookmarks
        recursive: Whether to scan subdirectories
        formats: List of formats to import ['html', 'markdown', 'json', 'csv', 'nbf']
                If None, imports all supported formats
    """
    if formats is None:
        formats = ['html', 'markdown', 'json', 'csv', 'nbf']
    
    # Track statistics
    stats = {
        'files_processed': 0,
        'bookmarks_imported': 0,
        'errors': []
    }
    
    # Define file extensions for each format
    format_extensions = {
        'html': ['.html', '.htm'],
        'markdown': ['.md', '.markdown', '.mdown'],
        'json': ['.json'],
        'csv': ['.csv'],
        'nbf': ['.html', '.htm']  # Will check content for Netscape format
    }
    
    # Build list of extensions to look for
    extensions = set()
    for fmt in formats:
        if fmt in format_extensions:
            extensions.update(format_extensions[fmt])
    
    # Walk directory
    import glob
    pattern = '**/*' if recursive else '*'
    
    for file_path in Path(directory).glob(pattern):
        if not file_path.is_file():
            continue
            
        # Check if file has a supported extension
        if not any(file_path.suffix.lower() == ext for ext in extensions):
            continue
        
        file_str = str(file_path)
        initial_count = len(bookmarks)
        
        try:
            # Determine format and import
            if file_path.suffix.lower() in ['.md', '.markdown', '.mdown'] and 'markdown' in formats:
                console.print(f"[blue]Importing markdown: {file_path.name}[/blue]")
                bookmarks = import_bookmarks_markdown(file_str, bookmarks, lib_dir)
                stats['files_processed'] += 1
                
            elif file_path.suffix.lower() == '.json' and 'json' in formats:
                console.print(f"[blue]Importing JSON: {file_path.name}[/blue]")
                bookmarks = import_bookmarks_json(file_str, bookmarks, lib_dir)
                stats['files_processed'] += 1
                
            elif file_path.suffix.lower() == '.csv' and 'csv' in formats:
                console.print(f"[blue]Importing CSV: {file_path.name}[/blue]")
                bookmarks = import_bookmarks_csv(file_str, bookmarks, lib_dir, 
                                               ['url', 'title', 'tags', 'description', 'stars'])
                stats['files_processed'] += 1
                
            elif file_path.suffix.lower() in ['.html', '.htm']:
                # Check if it's Netscape format
                try:
                    with open(file_str, 'r', encoding='utf-8') as f:
                        content = f.read(1000)  # Read first 1000 chars
                    
                    if 'netscape' in content.lower() and 'nbf' in formats:
                        console.print(f"[blue]Importing Netscape bookmarks: {file_path.name}[/blue]")
                        bookmarks = import_bookmarks(file_str, bookmarks, lib_dir, format='netscape')
                        stats['files_processed'] += 1
                    elif 'html' in formats:
                        console.print(f"[blue]Importing HTML: {file_path.name}[/blue]")
                        bookmarks = import_bookmarks_html_generic(file_str, bookmarks, lib_dir)
                        stats['files_processed'] += 1
                except Exception as e:
                    if 'html' in formats:
                        # Fall back to generic HTML import
                        console.print(f"[blue]Importing HTML: {file_path.name}[/blue]")
                        bookmarks = import_bookmarks_html_generic(file_str, bookmarks, lib_dir)
                        stats['files_processed'] += 1
                    else:
                        raise
            
            # Count new bookmarks
            new_count = len(bookmarks) - initial_count
            stats['bookmarks_imported'] += new_count
            
        except Exception as e:
            error_msg = f"Error importing {file_path.name}: {str(e)}"
            logging.error(error_msg)
            stats['errors'].append(error_msg)
            console.print(f"[red]✗ {error_msg}[/red]")
    
    # Summary
    console.print(f"\n[green]Directory import complete:[/green]")
    console.print(f"  Files processed: {stats['files_processed']}")
    console.print(f"  Bookmarks imported: {stats['bookmarks_imported']}")
    if stats['errors']:
        console.print(f"  Errors: {len(stats['errors'])}")
        for err in stats['errors'][:5]:  # Show first 5 errors
            console.print(f"    - {err}")
        if len(stats['errors']) > 5:
            console.print(f"    ... and {len(stats['errors']) - 5} more errors")
    
    return bookmarks