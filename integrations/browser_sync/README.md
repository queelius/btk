# Browser Sync Integration

Two-way synchronization between BTK and browser bookmarks. Supports Chrome, Firefox, Edge, Brave, and Vivaldi.

## Features

- **Bidirectional Sync**: Keep BTK and browser in sync
- **Multi-Browser Support**: Chrome, Firefox, Edge, Brave, Vivaldi
- **Conflict Resolution**: Multiple strategies for handling conflicts
- **Change Detection**: Only syncs what's changed
- **Folder Mapping**: Browser folders become tags
- **Metadata Preservation**: Keeps both browser and BTK metadata

## Installation

No dependencies - uses direct file access to browser bookmark files.

## Usage

```python
from integrations.browser_sync.sync import BrowserSync, Browser, SyncDirection, ConflictResolution

# Initialize sync for Chrome
sync = BrowserSync(
    browser=Browser.CHROME,
    profile=None,  # None = default profile
    sync_dir=SyncDirection.BIDIRECTIONAL,
    conflict_strategy=ConflictResolution.NEWEST_WINS
)

# Read browser bookmarks
browser_bookmarks = sync.read_browser_bookmarks()
print(f"Found {len(browser_bookmarks)} bookmarks in Chrome")

# Sync with BTK
import btk.utils as utils
btk_bookmarks = utils.load_bookmarks('/path/to/library')

synced, stats = sync.sync(btk_bookmarks)

print(f"Added to BTK: {stats['added_to_btk']}")
print(f"Added to browser: {stats['added_to_browser']}")
print(f"Conflicts resolved: {stats['conflicts_resolved']}")

# Save synced bookmarks
utils.save_bookmarks('/path/to/library', synced)
```

## Supported Browsers

- **Chrome**: Linux, macOS, Windows
- **Firefox**: Linux, macOS, Windows
- **Edge**: Linux, macOS, Windows
- **Brave**: Linux, macOS, Windows
- **Vivaldi**: Linux, macOS, Windows

## Sync Directions

```python
# From browser to BTK only
sync = BrowserSync(sync_dir=SyncDirection.FROM_BROWSER)

# From BTK to browser only
sync = BrowserSync(sync_dir=SyncDirection.TO_BROWSER)

# Both ways (default)
sync = BrowserSync(sync_dir=SyncDirection.BIDIRECTIONAL)
```

## Conflict Resolution Strategies

```python
# BTK wins conflicts
ConflictResolution.BTK_WINS

# Browser wins conflicts
ConflictResolution.BROWSER_WINS

# Newest bookmark wins (based on modification time)
ConflictResolution.NEWEST_WINS  # Default

# Merge both (combine titles, merge tags)
ConflictResolution.MERGE

# Ask user (interactive)
ConflictResolution.ASK
```

## Folder → Tag Mapping

Browser folders are converted to BTK tags:

```
Browser:
  Bookmarks Bar/
    Programming/
      Python/
        Django Docs

BTK:
  {
    "url": "https://docs.djangoproject.com/",
    "title": "Django Docs",
    "tags": ["Programming", "Python"]
  }
```

## Examples

### Simple One-Way Import

```python
# Import from Firefox to BTK
sync = BrowserSync(
    browser=Browser.FIREFOX,
    sync_dir=SyncDirection.FROM_BROWSER
)

btk_bookmarks = []
synced, stats = sync.sync(btk_bookmarks)

print(f"Imported {len(synced)} bookmarks from Firefox")
```

### Periodic Sync

```python
import schedule
import time

def sync_bookmarks():
    sync = BrowserSync(browser=Browser.CHROME)
    btk_bookmarks = utils.load_bookmarks('/path/to/library')

    synced, stats = sync.sync(btk_bookmarks)
    utils.save_bookmarks('/path/to/library', synced)

    print(f"Sync complete: +{stats['added_to_btk']} bookmarks")

# Sync every hour
schedule.every().hour.do(sync_bookmarks)

while True:
    schedule.run_pending()
    time.sleep(60)
```

### Multi-Browser Sync

```python
# Collect from multiple browsers
all_browser_bookmarks = []

for browser in [Browser.CHROME, Browser.FIREFOX, Browser.EDGE]:
    try:
        sync = BrowserSync(browser=browser)
        bookmarks = sync.read_browser_bookmarks()
        all_browser_bookmarks.extend(bookmarks)
        print(f"{browser.value}: {len(bookmarks)} bookmarks")
    except Exception as e:
        print(f"Failed to read {browser.value}: {e}")

# Merge into BTK
# (deduplicate by URL first)
from collections import OrderedDict
unique = list(OrderedDict((b['url'], b) for b in all_browser_bookmarks).values())
```

## Bookmark Metadata

### Browser → BTK Mapping

```python
{
    'url': bookmark_url,
    'title': bookmark_title,
    'tags': folder_path,  # ['Folder', 'Subfolder']
    'added': datetime,
    'last_visited': datetime,
    'browser_id': internal_id,
    'browser_guid': guid,
    'source': 'browser:chrome'
}
```

### BTK Fields Preserved

During sync, BTK-specific fields are kept:
- `id`, `unique_id`
- `stars`
- `visit_count`
- `description`
- `favicon`
- Custom metadata

## Sync State

Sync state is tracked in `~/.btk/sync_state/{browser}_{profile}.json`:

```json
{
    "last_sync": "2024-01-15T10:30:00",
    "browser_hash": "abc123...",
    "btk_hash": "def456...",
    "synced_items": {
        "https://example.com": "hash123"
    }
}
```

## Browser File Locations

### Chrome/Chromium-based

- **Linux**: `~/.config/google-chrome/Default/Bookmarks`
- **macOS**: `~/Library/Application Support/Google/Chrome/Default/Bookmarks`
- **Windows**: `%LOCALAPPDATA%\Google\Chrome\User Data\Default\Bookmarks`

### Firefox

- **Linux**: `~/.mozilla/firefox/*.default*/places.sqlite`
- **macOS**: `~/Library/Application Support/Firefox/Profiles/*.default*/places.sqlite`
- **Windows**: `%APPDATA%\Mozilla\Firefox\Profiles\*.default*\places.sqlite`

## Limitations

- **Firefox**: Read-only (writing to places.sqlite is complex)
- **Browser must be closed**: For Chromium browsers during write operations
- **No real-time sync**: Manual or scheduled sync only
- **Tags → Folders**: BTK tags don't map back to browser folders (yet)

## Troubleshooting

### Bookmark File Not Found

```python
# Specify custom profile
sync = BrowserSync(
    browser=Browser.CHROME,
    profile='Profile 1'  # or 'Default'
)

# Check detected path
print(sync.bookmark_file)
```

### Permission Errors

```bash
# Ensure browser is closed
# Check file permissions
ls -l ~/.config/google-chrome/Default/Bookmarks
```

### Conflicting Changes

```python
# Use specific conflict resolution
sync = BrowserSync(
    conflict_strategy=ConflictResolution.BTK_WINS
)
```

## Best Practices

1. **Close browser during sync** (especially for write operations)
2. **Backup first**: Copy browser bookmarks before syncing
3. **Start with FROM_BROWSER**: Import first, then enable bidirectional
4. **Test with small profile**: Try with a test browser profile first
5. **Regular syncs**: Schedule frequent syncs for incremental changes

## License

Part of the BTK (Bookmark Toolkit) project.
