# BTK Chrome Extension

A Chrome extension for bookmark management with BTK REST API.

## Features

### Current Page Tab
- **Quick Add**: Add current page to BTK with tags and description
- **Bookmark Status**: See if current page is already bookmarked
- **Visit Tracking**: Manually track visits to bookmarked pages
- **Edit/Delete**: Modify or remove existing bookmarks

### Browse Tab
- **Recent Bookmarks**: View your 50 most recent bookmarks
- **Quick Actions**: Edit or delete any bookmark
- **Open URLs**: Click to open bookmarks in new tabs

### Search Tab
- **Full-Text Search**: Search across titles, URLs, descriptions, and tags
- **Real-Time Results**: Results update as you type
- **Quick Actions**: Edit, delete, or open search results

### General
- **Edit Modal**: Full edit form for title, URL, tags, description, and starred status
- **Server Settings**: Configure BTK server URL (defaults to localhost:8000)
- **Dashboard Link**: Quick access to the full BTK web dashboard

## Installation

### Development Mode

1. Start the BTK server:
   ```bash
   btk serve --port 8000
   ```

2. Open Chrome and navigate to `chrome://extensions/`

3. Enable "Developer mode" (toggle in top right)

4. Click "Load unpacked" and select this directory (`btk-chrome-extension`)

5. The BTK extension icon should appear in your toolbar

### Icons

Before loading the extension, you need to add icon files to the `icons/` directory:
- `icon16.png` (16x16)
- `icon32.png` (32x32)
- `icon48.png` (48x48)
- `icon128.png` (128x128)

You can create simple icons using any image editor or use a placeholder.

## Usage

1. **Configure Server URL**: Click the extension icon and set your BTK server URL (default: `http://localhost:8000`)

2. **Add Bookmark**: When on any page, click the extension icon to add it to BTK with optional tags and description

3. **View Status**: The extension shows if the current page is already bookmarked and its visit count

4. **Track Visits**: Click "Track Visit" to increment the visit counter for bookmarked pages

5. **Remove Bookmark**: Click "Remove Bookmark" to delete the bookmark

## Auto-Tracking (Optional)

The extension can automatically track visits to bookmarked pages. This feature is disabled by default. To enable:

1. Open the browser console on any page
2. Run: `chrome.storage.local.set({ btkAutoTrack: true })`

## Development

The extension consists of:
- `manifest.json` - Extension configuration (Manifest V3)
- `popup.html/js` - The popup UI when clicking the extension icon
- `background.js` - Service worker for background tasks

## Requirements

- Chrome 88+ (Manifest V3 support)
- BTK server running with REST API (`btk serve`)
