# Graph Analysis

BTK can build weighted similarity graphs to discover relationships between your bookmarks based on multiple factors:

- **Domain similarity**: Bookmarks from the same domain or related domains
- **Tag overlap**: Bookmarks sharing similar tags
- **Direct links**: When one bookmark links to another
- **Indirect links**: Multi-hop connections (optional)

## Building the Graph

```bash
# Build graph with default settings
btk graph build

# Build with custom weights and threshold
btk graph build \
  --domain-weight 1.0 \
  --tag-weight 2.0 \
  --direct-link-weight 5.0 \
  --min-edge-weight 4.0

# Only create strong connections (recommended for large datasets)
btk graph build --min-edge-weight 4.0
```

The `--min-edge-weight` threshold filters out weak connections, keeping only meaningful relationships. For 4,000+ bookmarks, use 4.0 or higher to avoid creating millions of edges.

### Progress Indicator

The build command shows a progress bar with:

- Real-time edge count
- Percentage complete
- Estimated time remaining

```
Building bookmark graph...
  Computing similarities (found 1042 edges)... ━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
Saving graph to database...

✓ Graph built successfully!
  Bookmarks: 4192
  Edges: 1042
  Avg edge weight: 4.24
  Max edge weight: 6.50
```

## Exploring Relationships

### Find Similar Bookmarks

```bash
# Find 10 most similar bookmarks
btk graph neighbors 42

# Find bookmarks with minimum weight threshold
btk graph neighbors 42 --min-weight 4.5

# Show more neighbors
btk graph neighbors 42 --limit 20
```

Output shows:

- Bookmark ID and title
- Total similarity weight
- Component breakdown (domain, tags, direct links)

```
┏━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━┳━━━━━━┓
┃ ID  ┃ Title             ┃ Weight ┃ Domain ┃ Tags ┃ Link ┃
┡━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━╇━━━━━━┩
│ 123 │ Python Tutorial   │ 4.50   │ 1.80   │ 2.70 │      │
│ 456 │ Flask Docs        │ 4.20   │ 1.80   │ 2.40 │      │
│ 789 │ Django Guide      │ 3.90   │ 1.50   │ 2.40 │      │
└─────┴───────────────────┴────────┴────────┴──────┴──────┘
```

### View Statistics

```bash
btk graph stats
```

Shows:

- Total edges in graph
- Average edge weight
- Breakdown by component (domain, tags, direct links)

## Exporting the Graph

BTK supports multiple export formats for different use cases:

### Visualization Formats

#### Interactive Web Viewer (D3.js)

```bash
# Export for interactive visualization
btk graph export graph.json --format d3 --min-weight 4.0

# Open viewer.html in browser and load graph.json
```

Features:

- Interactive force-directed layout
- Drag nodes to reposition
- Zoom and pan
- Hover tooltips with bookmark details
- Click to open URLs
- Filter by weight threshold
- Toggle labels on/off

#### Static Images (SVG/PNG)

```bash
# Export as SVG (vector graphics)
btk graph export graph.svg --format svg \
  --min-weight 4.0 \
  --width 2000 --height 2000

# Export as PNG (raster image)
btk graph export graph.png --format png \
  --min-weight 4.0 \
  --width 3000 --height 3000

# Export without labels for clean presentation
btk graph export graph.svg --format svg \
  --min-weight 5.0 \
  --no-labels
```

Features:

- Pre-computed force-directed layout
- Edge thickness shows relationship strength
- Node colors based on primary tag
- Gold outline for starred bookmarks
- White background (default)
- Customizable dimensions

### Network Analysis Formats

#### GEXF (Gephi Native Format)

```bash
# Best for Gephi
btk graph export graph.gexf --format gexf --min-weight 4.0
```

#### GraphML (Universal Format)

```bash
# Compatible with yEd, Gephi, Cytoscape, NetworkX
btk graph export graph.graphml --format graphml --min-weight 4.0
```

#### GML (Simple Text Format)

```bash
# Compact format, easy to parse
btk graph export graph.gml --format gml --min-weight 4.0
```

All network formats include:

- Node attributes: id, title, url, tags, starred status
- Edge attributes: weight, domain_weight, tag_weight, direct_link

## Gephi Workflow

[Gephi](https://gephi.org/) is a powerful network visualization tool. Here's how to analyze your bookmarks:

### 1. Export from BTK

```bash
btk graph export bookmarks.gexf --format gexf --min-weight 4.0
```

### 2. Import to Gephi

1. Open Gephi
2. File → Open → Select `bookmarks.gexf`
3. Choose "Undirected" graph type
4. Click OK

### 3. Apply Layout

In the Layout panel:

- Select "ForceAtlas 2" or "Fruchterman-Reingold"
- Adjust settings (repulsion strength, gravity)
- Click "Run"
- Stop when layout stabilizes

### 4. Analyze Network

In the Statistics panel, run:

- **Modularity**: Detect communities/clusters
- **PageRank**: Identify influential bookmarks
- **Betweenness Centrality**: Find bridge bookmarks
- **Degree Distribution**: Understand connectivity

### 5. Visual Styling

In the Appearance panel:

- **Nodes**:
  - Size by degree (more connections = larger)
  - Color by modularity class (communities)
  - Color by tag
- **Edges**:
  - Thickness by weight
  - Color by type (domain vs. tag vs. link)

### 6. Filter and Explore

In the Filters panel:

- Range filter on edge weight
- Partition by tags
- Degree range (highly connected nodes)
- Create sub-graphs of interesting clusters

### 7. Export Results

- File → Export → SVG/PDF/PNG
- Adjust settings for publication quality
- Export filtered views or specific communities

## Advanced Analysis

### Community Detection

Gephi's Modularity algorithm can automatically detect bookmark communities:

```python
# In Gephi:
# 1. Statistics → Modularity → Run
# 2. Appearance → Nodes → Partition → Modularity Class → Apply
```

Communities might represent:

- Different research topics
- Programming languages/frameworks
- Personal vs. professional bookmarks
- Learning resources vs. reference docs

### Identifying Hubs

High-degree nodes (many connections) are:

- **Topic hubs**: Central resources in a field
- **Reference materials**: Frequently related documents
- **Entry points**: Good starting points for exploration

Find hubs:

```python
# In Gephi:
# 1. Statistics → Average Degree → Run
# 2. Filter → Attributes → Degree → Range
# 3. Set minimum degree threshold
```

### Finding Bridges

High betweenness centrality indicates bridge bookmarks that connect different topics:

```python
# In Gephi:
# 1. Statistics → Network Diameter → Run (calculates betweenness)
# 2. Appearance → Nodes → Ranking → Betweenness Centrality
# 3. Size nodes by betweenness
```

## Use Cases

### Research Organization

Build a graph of research papers and:

- Identify citation clusters
- Find related work automatically
- Discover connections between topics
- Visualize literature landscapes

### Learning Paths

For programming/tutorial bookmarks:

- See prerequisite relationships
- Find complete learning sequences
- Identify foundational resources
- Discover related technologies

### Duplicate Detection

Strong domain + tag overlap might indicate:

- Duplicate bookmarks
- Mirror sites
- Updated versions of same resource

### Knowledge Mapping

Visualize your entire bookmark collection:

- See topic distributions
- Find gaps in knowledge areas
- Discover unexpected connections
- Plan future learning

## Configuration Reference

### Weight Components

```bash
--domain-weight FLOAT      # Weight for domain similarity (default: 1.0)
--tag-weight FLOAT         # Weight for tag overlap (default: 2.0)
--direct-link-weight FLOAT # Weight for direct hyperlinks (default: 5.0)
--indirect-link-weight     # Multi-hop connections (default: 0.0, disabled)
```

### Domain Similarity Calculation

- Base score: 1.0 for matching domain
- Subdomain bonus: +0.5 for exact subdomain match
- Path depth: +0.3 per matching path segment

Example:

- `docs.python.org/3/tutorial/` vs `docs.python.org/3/library/`
  - Same domain: 1.0
  - Same subdomain: +0.5
  - Matching path `/3/`: +0.3
  - **Total**: 1.8

### Tag Similarity (Jaccard Index)

```
similarity = |tags1 ∩ tags2| / |tags1 ∪ tags2|
```

Example:

- Bookmark A: `[python, web, flask]`
- Bookmark B: `[python, web, django]`
- Intersection: `{python, web}` = 2
- Union: `{python, web, flask, django}` = 4
- **Similarity**: 2/4 = 0.5
- **Weighted**: 0.5 × 2.0 (tag_weight) = 1.0

### Thresholds

```bash
--min-edge-weight FLOAT    # Don't create edges below this weight
--max-hops INT             # Maximum hops for indirect links (default: 3)
```

For large datasets (1000+ bookmarks):

- Use `--min-edge-weight 4.0` or higher
- This prevents O(n²) explosion
- Keeps only meaningful connections

## Tips & Best Practices

1. **Start with high threshold**: Use `--min-edge-weight 5.0` first, then lower if needed
2. **Export filtered views**: Use `--min-weight` on export to create focused visualizations
3. **Rebuild after changes**: Run `btk graph build` after adding many bookmarks or retag
ging
4. **Use communities for tagging**: Let Gephi detect communities, then add tags to match
5. **Export multiple formats**: SVG for presentations, GEXF for analysis
6. **Combine with search**: Use `btk graph neighbors` to find related content when researching

## Troubleshooting

### Too Many Edges

**Problem**: Graph has millions of edges, too slow to visualize

**Solution**: Rebuild with higher threshold

```bash
btk graph build --min-edge-weight 5.0
```

### Graph Too Sparse

**Problem**: Very few connections, isolated nodes

**Solution**: Lower threshold or adjust weights

```bash
btk graph build --min-edge-weight 2.0 --tag-weight 3.0
```

### Gephi Won't Open File

**Problem**: File too large

**Solution**: Export with higher min-weight filter

```bash
btk graph export graph.gexf --format gexf --min-weight 6.0
```

### PNG Export Fails

**Problem**: Missing cairosvg library

**Solution**: Install dependency

```bash
pip install cairosvg
```

## Next Steps

- [Import & Export](import-export.md) - Learn about other export formats
- [Tags & Organization](tags.md) - Optimize tags for better graph analysis
- [Plugin System](../advanced/plugins.md) - Create custom graph algorithms
