# Link Checker Integration

Check bookmark URLs for availability, redirects, SSL issues, and other problems to maintain bookmark quality.

## Features

- **Dead Link Detection**: Find 404s and other errors
- **Redirect Tracking**: Follow and record redirect chains
- **SSL Validation**: Check certificate validity
- **Response Time Monitoring**: Track slow sites
- **Concurrent Checking**: Fast parallel URL verification
- **Comprehensive Reports**: Detailed health reports

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

checker = registry.get_plugin('link_checker', 'bookmark_enricher')
bookmarks = utils.load_bookmarks('/path/to/library')

# Check all bookmarks
checked = checker.check_bookmarks(
    bookmarks=bookmarks,
    progress_callback=lambda b, r: print(f"Checked: {b['url']}")
)

# Find broken links
broken = checker.find_broken_links(bookmarks)

# Find redirects
redirects = checker.find_redirects(bookmarks)

# Generate report
report = checker.generate_report(checked)
print(f"Reachable: {report['reachable']}/{report['total_checked']}")
print(f"Broken: {report['broken']}")
print(f"Redirects: {report['redirects']}")
```

### Standalone Usage

```python
from integrations.link_checker.checker import LinkChecker

checker = LinkChecker(
    timeout=10,
    max_workers=5,
    follow_redirects=True,
    verify_ssl=True
)

# Check single URL
result = checker.check_url('https://example.com')
print(f"Status: {result['status_code']}")
print(f"Reachable: {result['reachable']}")
print(f"Response time: {result['response_time']}s")

# Get fix suggestions
fixes = checker.suggest_fixes(bookmark)
for action in fixes['suggested_actions']:
    print(f"- {action}")
```

## Check Results

Each check returns:

```python
{
    'url': 'https://example.com',
    'checked_at': '2024-01-15T10:30:00',
    'reachable': True,
    'status_code': 200,
    'status_category': 'success',  # success/redirect/client_error/server_error
    'error': None,
    'redirect_chain': [],  # List of redirects if any
    'final_url': 'https://example.com',
    'response_time': 0.45,  # seconds
    'ssl_valid': True,
    'headers': {
        'content-type': 'text/html',
        'server': 'nginx'
    }
}
```

## Configuration

```python
checker = LinkChecker(
    timeout=10,           # Request timeout in seconds
    max_workers=5,        # Concurrent requests
    follow_redirects=True, # Follow HTTP redirects
    verify_ssl=True       # Verify SSL certificates
)
```

## Examples

### Find and Fix Broken Links

```python
# Find all broken links
broken = checker.find_broken_links(bookmarks)

# Auto-fix redirects
for bookmark in bookmarks:
    if bookmark.get('link_check', {}).get('redirect_chain'):
        fixes = checker.suggest_fixes(bookmark)
        if fixes['auto_fixable']:
            bookmark['url'] = fixes['new_url']
            print(f"Updated {bookmark['title']} to {fixes['new_url']}")
```

### Generate Health Report

```python
checked = checker.check_bookmarks(bookmarks)
report = checker.generate_report(checked)

print(f"""
Bookmark Health Report:
  Total checked: {report['total_checked']}
  Reachable: {report['reachable']} ({report.get('reachable_percentage', 0)}%)
  Broken: {report['broken']} ({report.get('broken_percentage', 0)}%)
  Redirects: {report['redirects']}
  SSL issues: {report['ssl_issues']}
  Timeouts: {report['timeouts']}
  Slow links (>5s): {len(report['slow_links'])}
""")

# Show broken links
for link in report['broken_links']:
    print(f"❌ {link['title']}: {link['error']}")
```

### Monitor Link Health Over Time

```python
import btk.utils as utils

# Regular health checks
checked = checker.check_bookmarks(bookmarks)

# Save updated bookmarks with check metadata
utils.save_bookmarks(lib_dir, checked)

# Filter bookmarks that haven't been checked in 30 days
from datetime import datetime, timedelta
stale_threshold = datetime.now() - timedelta(days=30)

stale = [b for b in bookmarks
         if not b.get('link_check') or
         datetime.fromisoformat(b['link_check']['checked_at']) < stale_threshold]

# Re-check stale bookmarks
checker.check_bookmarks(stale)
```

## Report Structure

```python
{
    'total_checked': 1000,
    'reachable': 950,
    'broken': 50,
    'redirects': 25,
    'ssl_issues': 5,
    'timeouts': 3,
    'reachable_percentage': 95.0,
    'broken_percentage': 5.0,
    'by_status_category': {
        'success': 950,
        'client_error': 40,
        'server_error': 10
    },
    'broken_links': [...],  # List of broken bookmark details
    'redirect_links': [...], # List of redirected bookmarks
    'slow_links': [...],     # Bookmarks with response_time > 5s
    'generated_at': '2024-01-15T10:30:00'
}
```

## Performance

- **Concurrent Checking**: Uses ThreadPoolExecutor for parallel requests
- **Smart HEAD Requests**: Uses HEAD first, falls back to GET for 4xx/5xx
- **Rate Limiting**: Respects server limits (configurable delay)
- **Caching**: Results stored in bookmark metadata

Typical speeds:
- 100 bookmarks: ~20-30 seconds (with 5 workers)
- 1000 bookmarks: ~3-5 minutes (with 5 workers)

## Troubleshooting

### Too Many Timeouts

```python
# Increase timeout
checker = LinkChecker(timeout=30)

# Reduce concurrency to avoid rate limiting
checker = LinkChecker(max_workers=2)
```

### SSL Certificate Errors

```python
# Disable SSL verification (not recommended for production)
checker = LinkChecker(verify_ssl=False)
```

### Rate Limiting

```python
# Reduce concurrent workers
checker = LinkChecker(max_workers=2)

# Add delays between requests (modify source if needed)
```

## License

Part of the BTK (Bookmark Toolkit) project.
