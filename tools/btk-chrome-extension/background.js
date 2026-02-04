// BTK Chrome Extension - Background Service Worker

// ============================================================================
// Context Menu Setup
// ============================================================================

chrome.runtime.onInstalled.addListener(() => {
  // Create context menus
  chrome.contextMenus.create({
    id: 'btk-add-page',
    title: 'Add page to BTK',
    contexts: ['page']
  });

  chrome.contextMenus.create({
    id: 'btk-add-link',
    title: 'Add link to BTK',
    contexts: ['link']
  });

  chrome.contextMenus.create({
    id: 'btk-add-selection',
    title: 'Add page with selected text as description',
    contexts: ['selection']
  });

  chrome.contextMenus.create({
    id: 'separator-1',
    type: 'separator',
    contexts: ['page', 'link']
  });

  chrome.contextMenus.create({
    id: 'btk-star-page',
    title: 'Star this page in BTK',
    contexts: ['page']
  });

  console.log('BTK: Context menus created');
});

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const serverUrl = await getServerUrl();

  switch (info.menuItemId) {
    case 'btk-add-page':
      await addBookmark(serverUrl, tab.url, tab.title);
      break;

    case 'btk-add-link':
      await addBookmark(serverUrl, info.linkUrl, info.linkUrl);
      break;

    case 'btk-add-selection':
      await addBookmark(serverUrl, tab.url, tab.title, info.selectionText);
      break;

    case 'btk-star-page':
      await toggleStar(serverUrl, tab.url);
      break;
  }
});

// ============================================================================
// Keyboard Shortcuts
// ============================================================================

chrome.commands.onCommand.addListener(async (command) => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.url || tab.url.startsWith('chrome://')) return;

  const serverUrl = await getServerUrl();

  switch (command) {
    case 'quick-add':
      await addBookmark(serverUrl, tab.url, tab.title);
      showNotification('Bookmark added!');
      break;

    case 'toggle-star':
      const result = await toggleStar(serverUrl, tab.url);
      if (result !== null) {
        showNotification(result ? 'Starred!' : 'Unstarred');
      }
      break;
  }
});

// ============================================================================
// Badge Management
// ============================================================================

// Update badge when tab changes
chrome.tabs.onActivated.addListener(async (activeInfo) => {
  const tab = await chrome.tabs.get(activeInfo.tabId);
  await updateBadge(tab);
});

// Update badge when URL changes
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete') {
    await updateBadge(tab);

    // Also handle auto-tracking
    await handleAutoTrack(tab);
  }
});

async function updateBadge(tab) {
  if (!tab || !tab.url || tab.url.startsWith('chrome://')) {
    chrome.action.setBadgeText({ text: '' });
    return;
  }

  try {
    const serverUrl = await getServerUrl();
    const bookmark = await findBookmark(serverUrl, tab.url);

    if (bookmark) {
      // Show star if bookmarked and starred
      if (bookmark.stars) {
        chrome.action.setBadgeText({ text: '★' });
        chrome.action.setBadgeBackgroundColor({ color: '#f59e0b' });
      } else {
        chrome.action.setBadgeText({ text: '✓' });
        chrome.action.setBadgeBackgroundColor({ color: '#10b981' });
      }
    } else {
      chrome.action.setBadgeText({ text: '' });
    }
  } catch (error) {
    chrome.action.setBadgeText({ text: '' });
  }
}

// ============================================================================
// Auto-tracking (opt-in)
// ============================================================================

async function handleAutoTrack(tab) {
  if (!tab.url || tab.url.startsWith('chrome://')) return;

  try {
    const { btkAutoTrack } = await chrome.storage.local.get(['btkAutoTrack']);
    if (!btkAutoTrack) return;

    const serverUrl = await getServerUrl();
    const bookmark = await findBookmark(serverUrl, tab.url);

    if (bookmark) {
      // Update visit count
      await fetch(`${serverUrl}/bookmarks/${bookmark.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          visit_count: (bookmark.visit_count || 0) + 1,
          last_visited: new Date().toISOString()
        })
      });

      console.log(`BTK: Tracked visit for ${tab.url}`);
    }
  } catch (error) {
    console.log('BTK: Could not track visit', error.message);
  }
}

// ============================================================================
// Helper Functions
// ============================================================================

async function getServerUrl() {
  const { btkServerUrl } = await chrome.storage.local.get(['btkServerUrl']);
  return btkServerUrl || 'http://localhost:8000';
}

async function findBookmark(serverUrl, url) {
  try {
    const response = await fetch(`${serverUrl}/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: url })
    });

    if (!response.ok) return null;

    const bookmarks = await response.json();
    return bookmarks.find(b => b.url === url) || null;
  } catch (error) {
    return null;
  }
}

async function addBookmark(serverUrl, url, title, description = '') {
  try {
    const response = await fetch(`${serverUrl}/bookmarks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, title, description })
    });

    if (response.ok) {
      const bookmark = await response.json();
      console.log('BTK: Bookmark added', bookmark.id);

      // Update badge
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab && tab.url === url) {
        await updateBadge(tab);
      }

      return bookmark;
    }
  } catch (error) {
    console.error('BTK: Failed to add bookmark', error);
  }
  return null;
}

async function toggleStar(serverUrl, url) {
  try {
    const bookmark = await findBookmark(serverUrl, url);

    if (bookmark) {
      // Toggle star on existing bookmark
      const newStars = !bookmark.stars;
      const response = await fetch(`${serverUrl}/bookmarks/${bookmark.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stars: newStars })
      });

      if (response.ok) {
        // Update badge
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab) await updateBadge(tab);

        return newStars;
      }
    } else {
      // Add new bookmark with star
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab) {
        const response = await fetch(`${serverUrl}/bookmarks`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            url: url,
            title: tab.title,
            stars: true
          })
        });

        if (response.ok) {
          await updateBadge(tab);
          return true;
        }
      }
    }
  } catch (error) {
    console.error('BTK: Failed to toggle star', error);
  }
  return null;
}

function showNotification(message) {
  // Use chrome.notifications if available, otherwise just log
  if (chrome.notifications) {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon48.png',
      title: 'BTK',
      message: message
    });
  }
  console.log('BTK:', message);
}

// ============================================================================
// Message Handling
// ============================================================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'getServerUrl') {
    getServerUrl().then(serverUrl => {
      sendResponse({ serverUrl });
    });
    return true;
  }

  if (message.type === 'updateBadge') {
    chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
      if (tab) updateBadge(tab);
    });
  }

  if (message.type === 'refreshBadge') {
    chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
      if (tab) updateBadge(tab);
      sendResponse({ success: true });
    });
    return true;
  }
});
