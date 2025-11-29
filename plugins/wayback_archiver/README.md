# Wayback Machine Archiver Integration

Archive bookmarks to the Internet Archive's Wayback Machine for permanent preservation. Ensures your bookmarked content survives even if the original site goes down.

## Features

- **Automatic Archival**: Submit URLs to Wayback Machine
- **Snapshot Tracking**: Record archive URLs and timestamps
- **Bulk Archiving**: Archive multiple URLs with rate limiting
- **Smart Re-archival**: Only re-archive if >30 days old
- **Archive Status Checking**: Query existing snapshots
- **Snapshot Statistics**: Track total archives per URL

## Installation

```bash
pip install requests
```

## Usage

### As a BTK Plugin

```python
from btk.plugins import PluginRegistry
import btk.utils as utils

registry = PluginRegistry()
registry.discover_plugins()

archiver = registry.get_plugin('wayback_archiver', 'bookmark_enricher')
bookmarks = utils.load_bookmarks('/path/to/library')

# Archive a single bookmark
bookmark = bookmarks[0]
enriched = archiver.enrich(bookmark)

# Check archival status
if 'wayback' in enriched:
    print(f"Archived: {enriched['wayback']['archive_url']}")
    print(f"Snapshots: {enriched['wayback']['total_snapshots']}")
```

### Standalone Usage

```python
from integrations.wayback_archiver.archiver import WaybackArchiver

archiver = WaybackArchiver(timeout=30, rate_limit_delay=1.0)

# Check if URL is archived
status = archiver.check_archive_status('https://example.com')
if status:
    print(f"Latest snapshot: {status['timestamp']}")
    print(f"Archive URL: {status['url']}")
    print(f"Total snapshots: {status['total_snapshots']}")

# Archive a URL
result = archiver.archive_url('https://example.com')
if result['success']:
    print(f"Archived: {result['archive_url']}")
```

## Bookmark Enrichment

The archiver adds a `wayback` field to bookmarks:

```python
{
    'url': 'https://example.com',
    'title': 'Example Site',
    'wayback': {
        'last_archived': '2024-01-15T10:30:00',
        'archive_url': 'https://web.archive.org/web/20240115103000/https://example.com',
        'job_id': 'abc123',
        'latest_snapshot': '20240115103000',
        'latest_snapshot_url': 'https://web.archive.org/web/...',
        'total_snapshots': 42
    }
}
```

## Archive Status Check

```python
status = archiver.check_archive_status('https://example.com')

# Returns:
{
    'available': True,
    'url': 'https://web.archive.org/web/...',
    'timestamp': '20240115103000',  # Format: YYYYMMDDhhmmss
    'status': '200',
    'total_snapshots': 42
}
```

## Bulk Archiving

```python
urls = [bookmark['url'] for bookmark in bookmarks]

def progress(url, result):
    if result['success']:
        print(f"✓ Archived: {url}")
    else:
        print(f"✗ Failed: {url} - {result['error']}")

results = archiver.bulk_archive(urls, callback=progress)

# Results is a dict: url -> result
for url, result in results.items():
    if result['success']:
        print(f"{url} -> {result['archive_url']}")
```

## Smart Re-archival Logic

The archiver automatically checks existing snapshots:

- **Skip if archived < 7 days ago** (in bulk operations)
- **Re-archive if > 30 days old** (in enrichment)
- **Track last archival attempt** (even if failed)

```python
# Enrich bookmarks (respects 30-day threshold)
for bookmark in bookmarks:
    archiver.enrich(bookmark)  # Only archives if needed

# Force archival regardless of age
result = archiver.archive_url(bookmark['url'])
```

## Configuration

```python
archiver = WaybackArchiver(
    timeout=30,              # Request timeout in seconds
    rate_limit_delay=1.0     # Delay between requests (seconds)
)
```

**Important**: The Wayback Machine has rate limits. The default `rate_limit_delay=1.0` respects these limits.

## Examples

### Archive All Bookmarks

```python
import btk.utils as utils

bookmarks = utils.load_bookmarks('/path/to/library')
archiver = WaybackArchiver()

for i, bookmark in enumerate(bookmarks):
    print(f"[{i+1}/{len(bookmarks)}] Archiving {bookmark['url']}")
    enriched = archiver.enrich(bookmark)

utils.save_bookmarks('/path/to/library', bookmarks)
```

### Find Unarchived Bookmarks

```python
unarchived = []

for bookmark in bookmarks:
    if 'wayback' not in bookmark:
        unarchived.append(bookmark)
    else:
        # Check if archive is stale (>90 days)
        from datetime import datetime, timedelta
        last_archived = datetime.fromisoformat(
            bookmark['wayback']['last_archived']
        )
        if datetime.now() - last_archived > timedelta(days=90):
            unarchived.append(bookmark)

print(f"Found {len(unarchived)} unarchived/stale bookmarks")
```

### Verify Archives

```python
missing = []

for bookmark in bookmarks:
    status = archiver.check_archive_status(bookmark['url'])
    if not status or not status['available']:
        missing.append(bookmark)
        print(f"Not archived: {bookmark['title']}")

# Archive missing ones
archiver.bulk_archive([b['url'] for b in missing])
```

## Use Cases

### Backup Important Content

```python
# Archive only starred bookmarks
starred = [b for b in bookmarks if b.get('stars', 0) > 0]

for bookmark in starred:
    archiver.enrich(bookmark)
```

### Periodic Archival Task

```python
import schedule
import time

def archive_new_bookmarks():
    bookmarks = utils.load_bookmarks('/path/to/library')
    archiver = WaybackArchiver()

    new = [b for b in bookmarks if 'wayback' not in b]
    if new:
        archiver.bulk_archive([b['url'] for b in new])
        utils.save_bookmarks('/path/to/library', bookmarks)
        print(f"Archived {len(new)} new bookmarks")

# Run daily at 2 AM
schedule.every().day.at("02:00").do(archive_new_bookmarks)

while True:
    schedule.run_pending()
    time.sleep(3600)
```

## Snapshot Count API

```python
# Get total number of snapshots
count = archiver.get_snapshot_count('https://example.com')
print(f"Total snapshots: {count}")
```

## Troubleshooting

### Rate Limiting

```python
# Increase delay between requests
archiver = WaybackArchiver(rate_limit_delay=2.0)

# Or reduce concurrent operations
for bookmark in bookmarks[:10]:  # Process in batches
    archiver.enrich(bookmark)
    time.sleep(1)  # Extra delay
```

### Timeout Errors

```python
# Increase timeout for slow archival
archiver = WaybackArchiver(timeout=60)
```

### Failed Archives

```python
# Check error messages
result = archiver.archive_url(url)
if not result['success']:
    print(f"Error: {result['error']}")

# Common errors:
# - "Request timeout" - Increase timeout
# - Site blocks Wayback crawler
# - Content too large/complex
```

## Wayback Machine API

### Save API

```
GET https://web.archive.org/save/https://example.com
```

### Availability API

```
GET https://archive.org/wayback/available?url=https://example.com
```

### CDX API (Snapshot Count)

```
GET http://web.archive.org/cdx/search/cdx?url=https://example.com&showNumPages=true
```

## Best Practices

1. **Respect Rate Limits**: Use the built-in `rate_limit_delay`
2. **Archive Incrementally**: Don't try to archive thousands at once
3. **Check Before Archiving**: Use `check_archive_status()` to avoid duplicates
4. **Handle Failures Gracefully**: Some sites can't be archived
5. **Periodic Re-archival**: Archive important content regularly

## License

Part of the BTK (Bookmark Toolkit) project.
