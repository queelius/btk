# Readability Content Extractor Integration

Extract clean, readable content from web pages using readability heuristics. Makes bookmarks more searchable and useful by extracting main article content.

## Features

- **Clean Content Extraction**: Removes ads, navigation, and clutter
- **Metadata Extraction**: Author, publication date, excerpt
- **Reading Time Estimation**: Based on word count (~250 wpm)
- **Multi-Source Metadata**: Open Graph, Twitter Cards, Schema.org
- **Language Detection**: Automatic language identification
- **Smart Content Selection**: Finds main article using multiple heuristics

## Installation

```bash
pip install requests beautifulsoup4
```

## Usage

### As a BTK Plugin

```python
from btk.plugins import PluginRegistry

registry = PluginRegistry()
registry.discover_plugins()

extractor = registry.get_plugin('readability_extractor', 'content_extractor')

# Extract content from URL
result = extractor.extract('https://example.com/article')

print(f"Title: {result['title']}")
print(f"Author: {result['author']}")
print(f"Reading time: {result['reading_time']} min")
print(f"Word count: {result['word_count']}")
print(f"Content: {result['content'][:500]}...")
```

### Standalone Usage

```python
from integrations.readability_extractor.extractor import ReadabilityExtractor

extractor = ReadabilityExtractor(
    timeout=10,
    max_content_length=50000
)

result = extractor.extract('https://blog.example.com/post')

if result['success']:
    print(result['content'])
else:
    print(f"Extraction failed: {result['error']}")
```

## Extraction Result

```python
{
    'success': True,
    'url': 'https://example.com/article',
    'title': 'Article Title',
    'author': 'Author Name',
    'published_date': '2024-01-15',
    'excerpt': 'Article summary...',
    'content': 'Full cleaned article content...',
    'word_count': 1250,
    'reading_time': 5,  # minutes
    'language': 'en',
    'domain': 'example.com',
    'extracted_at': '2024-01-15T10:30:00',
    'error': None
}
```

## Content Extraction Strategy

The extractor uses multiple heuristics:

1. **Semantic HTML**: Checks `<article>` and `<main>` tags first
2. **Common Selectors**: Tries `.content`, `.article-content`, `#main-content`, etc.
3. **Paragraph Density**: Finds container with most `<p>` tags
4. **Schema.org**: Extracts structured data if available
5. **Fallback**: Collects all paragraphs if no clear main content

## Metadata Sources

### Open Graph

```html
<meta property="og:title" content="Article Title">
<meta property="og:description" content="Summary...">
```

### Twitter Cards

```html
<meta name="twitter:title" content="Article Title">
<meta name="twitter:creator" content="@author">
```

### Schema.org JSON-LD

```html
<script type="application/ld+json">
{
  "@type": "Article",
  "author": {"name": "Author"},
  "datePublished": "2024-01-15"
}
</script>
```

### Standard Meta Tags

```html
<meta name="author" content="Author Name">
<meta name="description" content="Article summary">
```

## Configuration

```python
extractor = ReadabilityExtractor(
    timeout=10,              # Request timeout in seconds
    max_content_length=50000 # Max content to store (chars)
)
```

## Examples

### Enrich Bookmarks with Content

```python
import btk.utils as utils

bookmarks = utils.load_bookmarks('/path/to/library')
extractor = ReadabilityExtractor()

for bookmark in bookmarks:
    if not bookmark.get('content'):
        result = extractor.extract(bookmark['url'])
        if result['success']:
            bookmark['content'] = result['content']
            bookmark['word_count'] = result['word_count']
            bookmark['reading_time'] = result['reading_time']
            bookmark['author'] = result.get('author')
            bookmark['published_date'] = result.get('published_date')

utils.save_bookmarks('/path/to/library', bookmarks)
```

### Extract for Semantic Search

```python
from integrations.readability_extractor.extractor import ReadabilityExtractor
from integrations.semantic_search.search import SemanticSearchEngine

extractor = ReadabilityExtractor()
search_engine = SemanticSearchEngine()

# Extract content for better embeddings
for bookmark in bookmarks:
    if not bookmark.get('content'):
        result = extractor.extract(bookmark['url'])
        if result['success']:
            bookmark['content'] = result['content']

# Now create embeddings with full content
embeddings = search_engine.create_embeddings(bookmarks)
```

### Filter by Reading Time

```python
# Find short articles (<5 min read)
short_articles = [b for b in bookmarks
                  if b.get('reading_time', 999) < 5]

# Find long-form content (>15 min read)
long_form = [b for b in bookmarks
             if b.get('reading_time', 0) > 15]
```

## Cleaning Process

The extractor:

1. **Removes clutter**: Scripts, styles, navigation, footers, ads
2. **Filters short lines**: Removes likely menu items (<20 chars)
3. **Removes boilerplate**: Common navigation text patterns
4. **Limits line length**: Removes likely code/data lines
5. **Collapses whitespace**: Normalizes spacing

## Troubleshooting

### Extraction Fails

```python
# Check the error
result = extractor.extract(url)
if not result['success']:
    print(f"Error: {result['error']}")

# Common issues:
# - Page requires JavaScript (use Selenium integration)
# - Content behind login/paywall
# - Unusual page structure
```

### Wrong Content Extracted

```python
# Inspect what was found
result = extractor.extract(url)
print(f"Extraction method: {result.get('method', 'unknown')}")

# Try manual content selection
from bs4 import BeautifulSoup
import requests

response = requests.get(url)
soup = BeautifulSoup(response.text, 'html.parser')
content = soup.select_one('.custom-content-class')
```

### Timeout Issues

```python
# Increase timeout for slow sites
extractor = ReadabilityExtractor(timeout=30)
```

## Performance

- **Speed**: 1-3 seconds per page (network dependent)
- **Success Rate**: ~85% for standard article pages
- **Content Quality**: Good for blog posts, news articles, documentation
- **Limitations**: Struggles with JavaScript-heavy sites, dynamic content

## Best Used For

✅ Blog posts and articles
✅ News sites
✅ Documentation pages
✅ Static content sites
✅ Medium, Dev.to, personal blogs

❌ Single-page applications (SPAs)
❌ Heavy JavaScript sites
❌ Streaming content
❌ Social media feeds

## License

Part of the BTK (Bookmark Toolkit) project.
