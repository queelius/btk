"""
BTK Visualization Module - Core visualization functionality
"""

from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
import logging
import networkx as nx
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import matplotlib.pyplot as plt
from pyvis.network import Network
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from rich.table import Table
from rich.console import Console
from colorama import init as colorama_init, Fore, Style
import json

# Initialize colorama and rich console
colorama_init(autoreset=True)
console = Console()

def extract_urls(html_content, base_url, bookmark_urls=None, max_mentions=50):
    """Extract a limited number of absolute URLs from the HTML content.
    
    If bookmark_urls is provided, only include URLs present in this set.
    """
    try:
        soup = BeautifulSoup(html_content, 'lxml')  # Use 'lxml' parser for robustness
    except Exception as e:
        logging.warning(f"lxml parser failed: {e}. Falling back to 'html.parser'.")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
        except Exception as e:
            logging.error(f"html.parser also failed: {e}. Skipping this content.")
            return set()
    
    urls = set()
    for link in soup.find_all('a', href=True):
        href = link['href']
        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.scheme in ('http', 'https'):
            if bookmark_urls is None or full_url in bookmark_urls:
                if full_url != base_url:  # Prevent self-loop by excluding the bookmark's own URL
                    urls.add(full_url)
                    if len(urls) >= max_mentions:
                        break
    return urls

def create_session(retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 504), ignore_ssl=False):
    """Create a requests session with retry logic."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    if ignore_ssl:
        session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return session

def fetch_bookmark_urls(bookmark, session, bookmark_urls=None):
    """Fetch URLs mentioned in a bookmark's webpage."""
    url = bookmark['url']
    unique_id = bookmark['unique_id']
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        mentioned_urls = extract_urls(response.text, url, bookmark_urls)
        return unique_id, mentioned_urls
    except requests.RequestException as e:
        logging.warning(f"Failed to fetch {url}: {e}")
        return unique_id, set()

def generate_url_graph(bookmarks, max_bookmarks=None, only_in_library=False, ignore_ssl=False, max_mentions=50):
    """Generate a directed graph from bookmarks based on URL mentions."""
    if max_bookmarks:
        bookmarks = bookmarks[:max_bookmarks]
    
    # Create a mapping from URL to unique_id for all bookmarks
    url_to_id = {bm['url']: bm['unique_id'] for bm in bookmarks}
    bookmark_urls = set(url_to_id.keys()) if only_in_library else None
    
    # Create a session for HTTP requests
    session = create_session(ignore_ssl=ignore_ssl)
    
    # Initialize the graph
    graph = nx.DiGraph()
    
    # Add nodes for each bookmark
    for bm in bookmarks:
        graph.add_node(bm['unique_id'], title=bm.get('title', 'Untitled'), url=bm['url'])
    
    # Fetch URLs mentioned in each bookmark concurrently
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        task = progress.add_task(f"[cyan]Fetching URLs from bookmarks...", total=len(bookmarks))
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all tasks
            future_to_bookmark = {
                executor.submit(fetch_bookmark_urls, bm, session, bookmark_urls): bm 
                for bm in bookmarks
            }
            
            # Process completed tasks
            for future in as_completed(future_to_bookmark):
                bookmark = future_to_bookmark[future]
                unique_id = bookmark['unique_id']
                try:
                    _, mentioned_urls = future.result()
                    # Add edges for each mentioned URL that is also a bookmark
                    for mentioned_url in mentioned_urls:
                        if mentioned_url in url_to_id:
                            target_id = url_to_id[mentioned_url]
                            graph.add_edge(unique_id, target_id)
                except Exception as e:
                    logging.error(f"Error processing bookmark {unique_id}: {e}")
                finally:
                    progress.update(task, advance=1)
    
    return graph

def visualize_graph(graph, bookmarks, output_file=None):
    """Visualize the bookmark graph using various formats."""
    if not output_file:
        # Default to interactive HTML
        output_file = 'bookmark_graph.html'
    
    output_format = output_file.split('.')[-1].lower()
    
    if output_format == 'html':
        visualize_interactive(graph, bookmarks, output_file)
    elif output_format == 'png':
        visualize_static(graph, bookmarks, output_file)
    elif output_format == 'json':
        export_graph_json(graph, bookmarks, output_file)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")

def visualize_interactive(graph, bookmarks, output_file):
    """Create an interactive HTML visualization using PyVis."""
    net = Network(height='800px', width='100%', directed=True)
    
    # Create a mapping for quick lookup
    id_to_bookmark = {bm['unique_id']: bm for bm in bookmarks}
    
    # Add nodes with labels and titles
    for node in graph.nodes():
        bookmark = id_to_bookmark[node]
        label = bookmark.get('title', 'Untitled')[:30]  # Truncate long titles
        title = f"{bookmark.get('title', 'Untitled')}\n{bookmark['url']}"
        net.add_node(node, label=label, title=title)
    
    # Add edges
    for source, target in graph.edges():
        net.add_edge(source, target)
    
    # Configure physics
    net.barnes_hut(gravity=-80000, central_gravity=0.3, spring_length=250)
    net.set_edge_smooth('dynamic')
    
    # Save the visualization
    net.save_graph(output_file)
    logging.info(f"Interactive visualization saved to {output_file}")

def visualize_static(graph, bookmarks, output_file):
    """Create a static PNG visualization using matplotlib."""
    plt.figure(figsize=(20, 20))
    
    # Create layout
    pos = nx.spring_layout(graph, k=3, iterations=50)
    
    # Create labels
    id_to_bookmark = {bm['unique_id']: bm for bm in bookmarks}
    labels = {node: id_to_bookmark[node].get('title', 'Untitled')[:20] for node in graph.nodes()}
    
    # Draw the graph
    nx.draw(graph, pos, labels=labels, with_labels=True, node_color='lightblue', 
            node_size=3000, font_size=8, font_weight='bold', arrows=True,
            edge_color='gray', alpha=0.6)
    
    plt.title("Bookmark URL Mention Graph", size=20)
    plt.axis('off')
    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()
    logging.info(f"Static visualization saved to {output_file}")

def export_graph_json(graph, bookmarks, output_file):
    """Export graph data as JSON."""
    id_to_bookmark = {bm['unique_id']: bm for bm in bookmarks}
    
    data = {
        'nodes': [
            {
                'id': node,
                'title': id_to_bookmark[node].get('title', 'Untitled'),
                'url': id_to_bookmark[node]['url']
            }
            for node in graph.nodes()
        ],
        'edges': [
            {'source': source, 'target': target}
            for source, target in graph.edges()
        ],
        'stats': {
            'total_nodes': graph.number_of_nodes(),
            'total_edges': graph.number_of_edges(),
            'density': nx.density(graph),
            'is_connected': nx.is_weakly_connected(graph)
        }
    }
    
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    logging.info(f"Graph data exported to {output_file}")

def display_graph_stats(graph, bookmarks):
    """Display statistics about the generated graph."""
    table = Table(title="Bookmark Graph Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    stats = [
        ("Total Bookmarks", str(len(bookmarks))),
        ("Nodes in Graph", str(graph.number_of_nodes())),
        ("Edges (Links)", str(graph.number_of_edges())),
        ("Graph Density", f"{nx.density(graph):.4f}"),
        ("Is Connected", "Yes" if nx.is_weakly_connected(graph) else "No"),
    ]
    
    # Find most connected nodes
    if graph.number_of_nodes() > 0:
        in_degrees = dict(graph.in_degree())
        out_degrees = dict(graph.out_degree())
        
        if in_degrees:
            max_in = max(in_degrees.items(), key=lambda x: x[1])
            stats.append(("Most Referenced", f"{max_in[0]} ({max_in[1]} links)"))
        
        if out_degrees:
            max_out = max(out_degrees.items(), key=lambda x: x[1])
            stats.append(("Most Linking", f"{max_out[0]} ({max_out[1]} links)"))
    
    for metric, value in stats:
        table.add_row(metric, value)
    
    console.print(table)