# Semantic Search Integration

Semantic search engine for BTK bookmarks using sentence embeddings. Find bookmarks by meaning and context rather than just keywords.

## Features

- **Semantic Search**: Search by meaning, not just keywords
- **Similarity Detection**: Find bookmarks similar to a given bookmark
- **Bookmark Clustering**: Group bookmarks by semantic similarity
- **Embedding Caching**: Fast performance with automatic caching
- **Fallback Support**: Graceful degradation to keyword search if models unavailable

## Installation

```bash
pip install sentence-transformers numpy scikit-learn
```

## Usage

### As a BTK Plugin

The semantic search engine automatically registers as a SearchEnhancer plugin:

```python
from btk.plugins import PluginRegistry
import btk.utils as utils

# Load plugin registry
registry = PluginRegistry()
registry.discover_plugins()

# Get semantic search engine
semantic_search = registry.get_plugin('semantic_search', 'search_enhancer')

# Load bookmarks
bookmarks = utils.load_bookmarks('/path/to/library')

# Semantic search
results = semantic_search.search(
    query="machine learning tutorials",
    bookmarks=bookmarks,
    top_k=10,
    threshold=0.3  # Minimum similarity score (0-1)
)

# Find similar bookmarks
similar = semantic_search.find_similar(
    bookmark=bookmarks[0],
    bookmarks=bookmarks,
    top_k=5,
    threshold=0.5
)

# Cluster bookmarks into semantic groups
clusters = semantic_search.cluster_bookmarks(
    bookmarks=bookmarks,
    n_clusters=5
)
```

### Standalone Usage

```python
from integrations.semantic_search.search import SemanticSearchEngine

# Initialize with custom model
engine = SemanticSearchEngine(
    model_name='all-MiniLM-L6-v2',  # Fast, lightweight model
    cache_dir='~/.btk/semantic_cache',
    device='cpu'  # or 'cuda' for GPU
)

# Perform semantic search
results = engine.search(
    query="python web frameworks",
    bookmarks=bookmarks,
    top_k=10
)

# Each result includes a semantic_score field
for bookmark in results:
    print(f"{bookmark['title']} (score: {bookmark['semantic_score']:.3f})")
```

## Configuration

### Model Selection

Choose from various sentence-transformer models:

```python
# Fast and lightweight (default)
engine = SemanticSearchEngine(model_name='all-MiniLM-L6-v2')

# Better quality, slower
engine = SemanticSearchEngine(model_name='all-mpnet-base-v2')

# Multilingual support
engine = SemanticSearchEngine(model_name='paraphrase-multilingual-MiniLM-L12-v2')

# Domain-specific models
engine = SemanticSearchEngine(model_name='msmarco-distilbert-base-v4')  # For search/IR
```

### GPU Acceleration

```python
# Use GPU for faster embedding generation
engine = SemanticSearchEngine(
    model_name='all-MiniLM-L6-v2',
    device='cuda'  # or 'cuda:0' for specific GPU
)
```

### Caching

Embeddings are automatically cached to disk for fast subsequent searches:

```python
# Custom cache directory
engine = SemanticSearchEngine(
    cache_dir='/custom/cache/path'
)

# Force rebuild embeddings
embeddings = engine.create_embeddings(
    bookmarks=bookmarks,
    force_rebuild=True
)
```

## How It Works

1. **Text Extraction**: Combines title, URL, description, tags, and content into searchable text
2. **Embedding Generation**: Uses sentence-transformers to create vector embeddings
3. **Similarity Calculation**: Computes cosine similarity between query and bookmark embeddings
4. **Ranking**: Returns bookmarks sorted by semantic relevance

## Searchable Fields

The engine extracts and combines:
- **Title** (highest weight)
- **URL** (domain and path)
- **Description**
- **Tags**
- **Content** (first 500 characters if available)

## Examples

### Search by Concept

```python
# Find machine learning resources (will match "neural networks", "deep learning", etc.)
results = engine.search("machine learning", bookmarks)

# Find data science tutorials
results = engine.search("data science tutorials", bookmarks)

# Find cloud computing resources
results = engine.search("cloud infrastructure deployment", bookmarks)
```

### Find Similar Bookmarks

```python
# Find bookmarks similar to a specific one
bookmark = bookmarks[42]
similar = engine.find_similar(
    bookmark=bookmark,
    bookmarks=bookmarks,
    top_k=5,
    threshold=0.5
)
```

### Semantic Clustering

```python
# Cluster bookmarks into semantic groups
clusters = engine.cluster_bookmarks(
    bookmarks=bookmarks,
    n_clusters=10
)

# Print cluster contents
for cluster_id, cluster_bookmarks in clusters.items():
    print(f"\nCluster {cluster_id}:")
    for bookmark in cluster_bookmarks[:5]:
        print(f"  - {bookmark['title']}")
```

## Performance

### Initial Setup
- First run downloads the model (~90MB for all-MiniLM-L6-v2)
- Initial embedding generation takes ~1-2 seconds per 100 bookmarks
- Embeddings are cached for subsequent searches

### Subsequent Searches
- Cached embeddings load in <1 second for 10,000 bookmarks
- Search queries process in <100ms for large collections

### GPU Acceleration
- 5-10x faster embedding generation with CUDA
- Minimal benefit for small collections (<1000 bookmarks)

## Models

### Recommended Models

| Model | Size | Speed | Quality | Use Case |
|-------|------|-------|---------|----------|
| all-MiniLM-L6-v2 | 80MB | Fast | Good | Default, general purpose |
| all-mpnet-base-v2 | 420MB | Slow | Excellent | Best quality |
| all-MiniLM-L12-v2 | 120MB | Medium | Better | Balanced |
| msmarco-distilbert-base-v4 | 250MB | Medium | Excellent | Search/retrieval optimized |

See [sentence-transformers models](https://www.sbert.net/docs/pretrained_models.html) for more options.

## Dependencies

- **sentence-transformers**: Sentence embedding models
- **numpy**: Array operations
- **scikit-learn**: K-means clustering (optional, for clustering feature)

## Troubleshooting

### Out of Memory

```python
# Use a smaller model
engine = SemanticSearchEngine(model_name='all-MiniLM-L6-v2')

# Process in batches for large collections
# (embedding generation automatically batches)
```

### Slow Performance

```python
# Enable GPU acceleration
engine = SemanticSearchEngine(device='cuda')

# Use faster model
engine = SemanticSearchEngine(model_name='all-MiniLM-L6-v2')

# Ensure embeddings are cached
engine.create_embeddings(bookmarks, force_rebuild=False)
```

### Model Download Issues

```python
# Pre-download model
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')

# Or specify custom cache directory
import os
os.environ['TRANSFORMERS_CACHE'] = '/custom/cache/path'
```

## Advanced Usage

### Custom Similarity Threshold

```python
# Strict matching (higher quality, fewer results)
results = engine.search(query, bookmarks, threshold=0.7)

# Relaxed matching (more results, lower quality)
results = engine.search(query, bookmarks, threshold=0.3)
```

### Integration with BTK Search

```python
# Combine with traditional search
from btk.tools import search_bookmarks

# First try semantic search
semantic_results = engine.search(query, bookmarks, top_k=20)

# Fall back to keyword search if few results
if len(semantic_results) < 5:
    keyword_results = search_bookmarks(bookmarks, query)
    results = semantic_results + keyword_results
```

## License

Part of the BTK (Bookmark Toolkit) project.
