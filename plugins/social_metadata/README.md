# Social Metadata Extractor Integration

Extract Open Graph, Twitter Card, and Schema.org metadata from web pages to enrich bookmarks with social sharing data.

## Features

- **Open Graph Metadata**: og:title, og:description, og:image, etc.
- **Twitter Cards**: twitter:title, twitter:description, twitter:image
- **Schema.org Data**: JSON-LD structured data
- **Standard Meta Tags**: author, keywords, description
- **Preview Images**: Social media preview images
- **Auto-Enrichment**: Fills missing bookmark fields

## Installation

```bash
pip install requests beautifulsoup4
```

## Usage

```python
from btk.plugins import PluginRegistry

registry = PluginRegistry()
registry.discover_plugins()

extractor = registry.get_plugin('social_metadata', 'bookmark_enricher')

# Enrich bookmark
bookmark = {'url': 'https://example.com'}
enriched = extractor.enrich(bookmark)

# Now has: title, description, preview_image, author, etc.
print(enriched['title'])
print(enriched['description'])
print(enriched['preview_image'])
```

## Extracted Metadata

```python
{
    'social_metadata': {
        'open_graph': {
            'title': 'Page Title',
            'description': 'Page description',
            'image': 'https://example.com/image.jpg',
            'site_name': 'Example Site',
            'type': 'article',
            'url': 'https://example.com'
        },
        'twitter_card': {
            'card': 'summary_large_image',
            'title': 'Page Title',
            'description': 'Description',
            'image': 'https://example.com/image.jpg',
            'creator': '@username'
        },
        'meta_tags': {
            'description': 'Page description',
            'author': 'Author Name',
            'keywords': 'keyword1, keyword2',
            'theme-color': '#ffffff'
        },
        'schema_org': [{
            '@type': 'Article',
            'author': {'name': 'Author'},
            'datePublished': '2024-01-15'
        }],
        'page_info': {
            'title': 'Page Title',
            'canonical_url': 'https://example.com/page',
            'favicon': 'https://example.com/favicon.ico',
            'language': 'en'
        }
    }
}
```

## Auto-Enrichment

The extractor automatically fills bookmark fields if empty:

```python
# Before
bookmark = {'url': 'https://example.com'}

# After enrichment
bookmark = {
    'url': 'https://example.com',
    'title': 'Extracted from og:title or <title>',
    'description': 'From og:description or meta description',
    'preview_image': 'From og:image or twitter:image',
    'site_name': 'From og:site_name',
    'author': 'From meta author or og:article:author',
    'published_date': 'From og:article:published_time',
    'tags': ['extracted', 'from', 'keywords'],  # From meta keywords
    'language': 'en',  # From HTML lang attribute
    'social_metadata': {...}  # Full metadata
}
```

## Examples

### Enrich All Bookmarks

```python
import btk.utils as utils

bookmarks = utils.load_bookmarks('/path/to/library')
extractor = SocialMetadataExtractor()

for bookmark in bookmarks:
    if not bookmark.get('description'):
        extractor.enrich(bookmark)

utils.save_bookmarks('/path/to/library', bookmarks)
```

### Get Preview Images

```python
# Extract preview images for all bookmarks
for bookmark in bookmarks:
    if not bookmark.get('preview_image'):
        extractor.enrich(bookmark)

# Now use preview images for display
print(bookmark['preview_image'])
```

## Configuration

```python
extractor = SocialMetadataExtractor(
    timeout=10,
    user_agent='Custom User Agent/1.0'
)
```

## License

Part of the BTK (Bookmark Toolkit) project.
