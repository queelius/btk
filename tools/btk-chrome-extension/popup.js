// BTK Chrome Extension - Popup Script

let serverUrl = 'http://localhost:8000';
let currentTab = null;
let existingBookmark = null;
let allBookmarks = [];
let currentBrowseView = 'recent';
let currentBrowseFilter = null; // For tag/domain drill-down

// Date navigation state
let dateNavigation = {
  year: null,
  month: null,
  day: null
};

// Initialize popup
document.addEventListener('DOMContentLoaded', async () => {
  // Load saved server URL
  const stored = await chrome.storage.local.get(['btkServerUrl']);
  if (stored.btkServerUrl) {
    serverUrl = stored.btkServerUrl;
    document.getElementById('serverUrl').value = serverUrl;
  }

  // Get current tab info
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  currentTab = tab;

  document.getElementById('pageTitle').textContent = tab.title || 'Untitled';
  document.getElementById('pageUrl').textContent = tab.url;

  // Setup event listeners
  setupListeners();

  // Setup event delegation for bookmark lists
  setupBookmarkListeners(document.getElementById('browseList'));
  setupBookmarkListeners(document.getElementById('searchResults'));

  // Check connection and load data
  await checkConnection();
});

function setupListeners() {
  // Settings toggle
  document.getElementById('settingsToggle').addEventListener('click', () => {
    document.getElementById('settingsPanel').classList.toggle('show');
  });

  // Server URL change
  document.getElementById('serverUrl').addEventListener('change', async (e) => {
    serverUrl = e.target.value.replace(/\/$/, '');
    await chrome.storage.local.set({ btkServerUrl: serverUrl });
    await checkConnection();
  });

  // Tab switching
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
  });

  // Add bookmark
  document.getElementById('addBtn').addEventListener('click', addBookmark);

  // Track visit
  document.getElementById('visitBtn').addEventListener('click', trackVisit);

  // Delete bookmark (current page)
  document.getElementById('deleteCurrentBtn').addEventListener('click', () => {
    if (existingBookmark) deleteBookmark(existingBookmark.id);
  });

  // Edit current bookmark
  document.getElementById('editCurrentBtn').addEventListener('click', () => {
    if (existingBookmark) openEditModal(existingBookmark);
  });

  // Search input
  let searchTimeout;
  document.getElementById('searchInput').addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => searchBookmarks(e.target.value), 300);
  });

  // Open dashboard
  document.getElementById('openDashboard').addEventListener('click', (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: serverUrl });
  });

  // Edit modal
  document.getElementById('closeEditModal').addEventListener('click', closeEditModal);
  document.getElementById('editModal').addEventListener('click', (e) => {
    if (e.target.id === 'editModal') closeEditModal();
  });
  document.getElementById('editForm').addEventListener('submit', saveEdit);
  document.getElementById('deleteFromEditBtn').addEventListener('click', () => {
    const id = document.getElementById('editId').value;
    if (id) deleteBookmark(parseInt(id));
  });

  // Browse sub-tabs
  document.querySelectorAll('.browse-tab').forEach(tab => {
    tab.addEventListener('click', () => switchBrowseView(tab.dataset.browse));
  });

  // Back button for tag/domain drill-down
  document.getElementById('browseBackBtn').addEventListener('click', () => {
    // Handle date navigation back
    if (currentBrowseView === 'dates') {
      if (dateNavigation.day) {
        dateNavigation.day = null;
      } else if (dateNavigation.month) {
        dateNavigation.month = null;
      } else if (dateNavigation.year) {
        dateNavigation.year = null;
      }
      loadDatesView(document.getElementById('browseList'));
      return;
    }
    currentBrowseFilter = null;
    loadBrowseList();
  });

  // Date field change
  document.getElementById('extDateField').addEventListener('change', () => {
    dateNavigation = { year: null, month: null, day: null };
    loadDatesView(document.getElementById('browseList'));
  });
}

function switchTab(tabName) {
  // Update tab buttons
  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === tabName);
  });

  // Update tab content
  document.querySelectorAll('.tab-content').forEach(c => {
    c.classList.toggle('active', c.id === `tab-${tabName}`);
  });

  // Load data for specific tabs
  if (tabName === 'browse') {
    loadBrowseList();
  } else if (tabName === 'search') {
    document.getElementById('searchInput').focus();
  }
}

async function checkConnection() {
  const statusEl = document.getElementById('connectionStatus');

  try {
    const response = await fetch(`${serverUrl}/stats`, { method: 'GET' });
    if (response.ok) {
      statusEl.textContent = 'Connected';
      statusEl.className = 'status connected';
      await Promise.all([
        checkBookmarkStatus(),
        loadAllBookmarks()
      ]);
    } else {
      throw new Error('Server returned error');
    }
  } catch (error) {
    statusEl.textContent = 'Disconnected';
    statusEl.className = 'status disconnected';
  }
}

async function loadAllBookmarks() {
  try {
    const response = await fetch(`${serverUrl}/bookmarks?limit=1000`);
    if (response.ok) {
      allBookmarks = await response.json();
    } else {
      console.error('loadAllBookmarks: bad response', response.status);
    }
  } catch (error) {
    console.error('loadAllBookmarks error:', error);
  }
}

async function checkBookmarkStatus() {
  if (!currentTab) return;

  const badge = document.getElementById('bookmarkStatusBadge');
  const statusIcon = document.getElementById('statusIcon');
  const statusText = document.getElementById('statusText');
  const addForm = document.getElementById('addForm');
  const existingForm = document.getElementById('existingForm');

  // First check local cache (faster, and more reliable after add/delete)
  existingBookmark = allBookmarks.find(b => b.url === currentTab.url);

  // If not found locally, also check server (in case local cache is stale)
  if (!existingBookmark) {
    try {
      const response = await fetch(`${serverUrl}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: currentTab.url })
      });

      if (response.ok) {
        const bookmarks = await response.json();
        existingBookmark = bookmarks.find(b => b.url === currentTab.url);
      }
    } catch (error) {
      console.error('Failed to search:', error);
    }
  }

  // Update UI based on existingBookmark
  if (existingBookmark) {
    badge.className = 'bookmark-status-badge bookmarked';
    statusIcon.textContent = '✓';
    let text = `Bookmarked (${existingBookmark.visit_count || 0} visits)`;
    if (existingBookmark.stars) text += ' ★';
    statusText.textContent = text;

    // Show existing bookmark details
    const tagsEl = document.getElementById('existingTags');
    if (existingBookmark.tags && existingBookmark.tags.length > 0) {
      tagsEl.innerHTML = existingBookmark.tags.map(t =>
        `<span class="tag">${escapeHtml(t)}</span>`
      ).join('');
    } else {
      tagsEl.innerHTML = '<span style="color: #9ca3af; font-size: 11px;">No tags</span>';
    }

    document.getElementById('existingDescription').textContent =
      existingBookmark.description || '-';

    addForm.style.display = 'none';
    existingForm.style.display = 'block';
  } else {
    badge.className = 'bookmark-status-badge not-bookmarked';
    statusIcon.textContent = '○';
    statusText.textContent = 'Not bookmarked';
    addForm.style.display = 'block';
    existingForm.style.display = 'none';
  }
}

function switchBrowseView(view) {
  currentBrowseView = view;
  currentBrowseFilter = null;

  // Reset date navigation when switching away from dates
  if (view !== 'dates') {
    dateNavigation = { year: null, month: null, day: null };
  }

  // Update browse tab buttons
  document.querySelectorAll('.browse-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.browse === view);
  });

  // Show/hide date options panel
  document.getElementById('dateOptionsPanel').style.display = view === 'dates' ? 'flex' : 'none';

  loadBrowseList();
}

function loadBrowseList() {
  const container = document.getElementById('browseList');
  const backHeader = document.getElementById('browseBackHeader');
  const backTitle = document.getElementById('browseBackTitle');
  const browseTabs = document.getElementById('browseTabs');

  if (allBookmarks.length === 0) {
    backHeader.style.display = 'none';
    browseTabs.style.display = 'flex';
    container.innerHTML = `
      <div class="empty-state">
        <p>📚</p>
        <p>No bookmarks yet</p>
      </div>
    `;
    return;
  }

  // If we're drilling down into a tag or domain
  if (currentBrowseFilter) {
    backHeader.style.display = 'flex';
    browseTabs.style.display = 'none';
    backTitle.textContent = currentBrowseFilter.name;

    let filtered;
    if (currentBrowseFilter.type === 'tag') {
      filtered = allBookmarks.filter(b =>
        b.tags && b.tags.includes(currentBrowseFilter.value)
      );
    } else if (currentBrowseFilter.type === 'domain') {
      filtered = allBookmarks.filter(b =>
        getDomain(b.url) === currentBrowseFilter.value
      );
    }

    container.innerHTML = filtered.map(b => renderBookmarkItem(b)).join('');
    return;
  }

  // Normal browse views
  backHeader.style.display = 'none';
  browseTabs.style.display = 'flex';

  switch (currentBrowseView) {
    case 'recent':
      loadRecentView(container);
      break;
    case 'starred':
      loadStarredView(container);
      break;
    case 'tags':
      loadTagsView(container);
      break;
    case 'domains':
      loadDomainsView(container);
      break;
    case 'dates':
      loadDatesView(container);
      break;
  }
}

function loadRecentView(container) {
  const sorted = [...allBookmarks].sort((a, b) =>
    new Date(b.added) - new Date(a.added)
  );
  container.innerHTML = sorted.slice(0, 50).map(b => renderBookmarkItem(b)).join('');
}

function loadStarredView(container) {
  const starred = allBookmarks.filter(b => b.stars);

  if (starred.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <p>⭐</p>
        <p>No starred bookmarks</p>
      </div>
    `;
    return;
  }

  const sorted = starred.sort((a, b) =>
    new Date(b.added) - new Date(a.added)
  );
  container.innerHTML = sorted.map(b => renderBookmarkItem(b)).join('');
}

function loadTagsView(container) {
  // Count tags
  const tagCounts = {};
  allBookmarks.forEach(b => {
    if (b.tags) {
      b.tags.forEach(tag => {
        tagCounts[tag] = (tagCounts[tag] || 0) + 1;
      });
    }
  });

  const sortedTags = Object.entries(tagCounts)
    .sort((a, b) => b[1] - a[1]);

  if (sortedTags.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <p>🏷️</p>
        <p>No tags yet</p>
      </div>
    `;
    return;
  }

  container.innerHTML = sortedTags.map(([tag, count], index) => `
    <div class="group-item" data-tag-index="${index}">
      <span class="group-name">${escapeHtml(tag)}</span>
      <span class="group-count">${count}</span>
    </div>
  `).join('');

  // Store tags for click handler
  window._tagsList = sortedTags.map(([tag]) => tag);

  // Add click handlers
  container.querySelectorAll('[data-tag-index]').forEach(el => {
    el.addEventListener('click', () => {
      const index = parseInt(el.dataset.tagIndex);
      const tag = window._tagsList[index];
      currentBrowseFilter = { type: 'tag', value: tag, name: `Tag: ${tag}` };
      loadBrowseList();
    });
  });
}

function loadDomainsView(container) {
  // Count domains
  const domainCounts = {};
  allBookmarks.forEach(b => {
    const domain = getDomain(b.url);
    domainCounts[domain] = (domainCounts[domain] || 0) + 1;
  });

  const sortedDomains = Object.entries(domainCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 50);

  if (sortedDomains.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <p>🌐</p>
        <p>No domains yet</p>
      </div>
    `;
    return;
  }

  container.innerHTML = sortedDomains.map(([domain, count], index) => `
    <div class="group-item" data-domain-index="${index}">
      <img src="https://www.google.com/s2/favicons?domain=${escapeHtml(domain)}&sz=32"
           class="bookmark-favicon" style="margin-right: 8px;"
           onerror="this.style.display='none'">
      <span class="group-name" style="flex: 1;">${escapeHtml(domain)}</span>
      <span class="group-count">${count}</span>
    </div>
  `).join('');

  // Store domains for click handler
  window._domainsList = sortedDomains.map(([domain]) => domain);

  // Add click handlers
  container.querySelectorAll('[data-domain-index]').forEach(el => {
    el.addEventListener('click', () => {
      const index = parseInt(el.dataset.domainIndex);
      const domain = window._domainsList[index];
      currentBrowseFilter = { type: 'domain', value: domain, name: domain };
      loadBrowseList();
    });
  });
}

function loadDatesView(container) {
  const field = document.getElementById('extDateField').value;
  const backHeader = document.getElementById('browseBackHeader');
  const backTitle = document.getElementById('browseBackTitle');
  const browseTabs = document.getElementById('browseTabs');
  const months = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  // Group bookmarks by date
  const grouped = {};
  allBookmarks.forEach(b => {
    const dateValue = field === 'added' ? b.added : b.last_visited;
    if (!dateValue) return;

    const date = new Date(dateValue);
    const year = date.getFullYear();
    const month = date.getMonth() + 1;
    const day = date.getDate();

    // Apply filters
    if (dateNavigation.year && year !== dateNavigation.year) return;
    if (dateNavigation.month && month !== dateNavigation.month) return;
    if (dateNavigation.day && day !== dateNavigation.day) return;

    // Generate key based on current navigation level
    let key;
    if (!dateNavigation.year) {
      key = String(year);
    } else if (!dateNavigation.month) {
      key = `${year}-${String(month).padStart(2, '0')}`;
    } else {
      key = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    }

    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(b);
  });

  // Sort keys in reverse chronological order
  const sortedKeys = Object.keys(grouped).sort().reverse();

  // Update back header
  if (dateNavigation.year) {
    let path = String(dateNavigation.year);
    if (dateNavigation.month) path += ` / ${months[dateNavigation.month]}`;
    if (dateNavigation.day) path += ` / ${dateNavigation.day}`;

    backHeader.style.display = 'flex';
    backTitle.textContent = path;
    browseTabs.style.display = 'flex';
  } else {
    backHeader.style.display = 'none';
  }

  // If at the day level, show the bookmarks directly
  if (dateNavigation.year && dateNavigation.month && dateNavigation.day) {
    const dayKey = `${dateNavigation.year}-${String(dateNavigation.month).padStart(2, '0')}-${String(dateNavigation.day).padStart(2, '0')}`;
    const bookmarks = grouped[dayKey] || [];
    if (bookmarks.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <p>📅</p>
          <p>No bookmarks on this day</p>
        </div>
      `;
    } else {
      container.innerHTML = bookmarks.map(b => renderBookmarkItem(b)).join('');
    }
    return;
  }

  // Show date groups
  if (sortedKeys.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <p>📅</p>
        <p>No bookmarks with ${field === 'added' ? 'added' : 'visited'} dates</p>
      </div>
    `;
    return;
  }

  container.innerHTML = sortedKeys.map((key, index) => {
    const parts = key.split('-');
    let label;
    if (parts.length === 1) {
      label = parts[0]; // Year
    } else if (parts.length === 2) {
      label = `${months[parseInt(parts[1])]} ${parts[0]}`; // Month Year
    } else {
      label = `${months[parseInt(parts[1])]} ${parseInt(parts[2])}, ${parts[0]}`; // Month Day, Year
    }

    return `
      <div class="group-item" data-date-index="${index}">
        <span class="group-name">${escapeHtml(label)}</span>
        <span class="group-count">${grouped[key].length}</span>
      </div>
    `;
  }).join('');

  // Store keys for click handler
  window._dateKeysList = sortedKeys;

  // Add click handlers
  container.querySelectorAll('[data-date-index]').forEach(el => {
    el.addEventListener('click', () => {
      const index = parseInt(el.dataset.dateIndex);
      const key = window._dateKeysList[index];
      const parts = key.split('-');

      if (parts.length === 1) {
        // Year clicked - drill down to months
        dateNavigation.year = parseInt(parts[0]);
        dateNavigation.month = null;
        dateNavigation.day = null;
      } else if (parts.length === 2) {
        // Month clicked - drill down to days
        dateNavigation.year = parseInt(parts[0]);
        dateNavigation.month = parseInt(parts[1]);
        dateNavigation.day = null;
      } else {
        // Day clicked - show bookmarks
        dateNavigation.year = parseInt(parts[0]);
        dateNavigation.month = parseInt(parts[1]);
        dateNavigation.day = parseInt(parts[2]);
      }

      loadDatesView(container);
    });
  });
}

async function searchBookmarks(query) {
  const container = document.getElementById('searchResults');

  if (!query.trim()) {
    container.innerHTML = `
      <div class="empty-state">
        <p>🔍</p>
        <p>Enter a search term above</p>
      </div>
    `;
    return;
  }

  container.innerHTML = '<div class="loading">Searching...</div>';

  try {
    const response = await fetch(`${serverUrl}/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });

    if (response.ok) {
      const results = await response.json();

      if (results.length === 0) {
        container.innerHTML = `
          <div class="empty-state">
            <p>😕</p>
            <p>No results for "${escapeHtml(query)}"</p>
          </div>
        `;
      } else {
        container.innerHTML = results.map(b => renderBookmarkItem(b)).join('');
      }
    }
  } catch (error) {
    container.innerHTML = `
      <div class="empty-state">
        <p>❌</p>
        <p>Search failed</p>
      </div>
    `;
  }
}

function renderBookmarkItem(bookmark) {
  const domain = getDomain(bookmark.url);
  const favicon = `https://www.google.com/s2/favicons?domain=${domain}&sz=32`;
  const isCurrent = currentTab && bookmark.url === currentTab.url;

  // Store bookmark data for click handlers
  if (!window._bookmarksMap) window._bookmarksMap = {};
  window._bookmarksMap[bookmark.id] = bookmark;

  return `
    <div class="bookmark-item ${isCurrent ? 'current' : ''}" data-bookmark-id="${bookmark.id}">
      <img src="${favicon}" class="bookmark-favicon" onerror="this.style.display='none'">
      <div class="bookmark-info" data-action="open" data-id="${bookmark.id}">
        <div class="bookmark-title">
          ${escapeHtml(bookmark.title || bookmark.url)}
          ${bookmark.stars ? '<span class="star">★</span>' : ''}
        </div>
        <div class="bookmark-url">${escapeHtml(domain)}</div>
        ${bookmark.tags && bookmark.tags.length > 0 ? `
          <div class="bookmark-tags">
            ${bookmark.tags.slice(0, 3).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('')}
            ${bookmark.tags.length > 3 ? `<span class="tag">+${bookmark.tags.length - 3}</span>` : ''}
          </div>
        ` : ''}
      </div>
      <div class="bookmark-actions">
        <button class="action-btn" data-action="edit" data-id="${bookmark.id}" title="Edit">✎</button>
        <button class="action-btn danger" data-action="delete" data-id="${bookmark.id}" title="Delete">✕</button>
      </div>
    </div>
  `;
}

// Setup event delegation for bookmark actions
function setupBookmarkListeners(container) {
  container.addEventListener('click', (e) => {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    const id = parseInt(actionEl.dataset.id);
    const bookmark = window._bookmarksMap[id];

    if (!bookmark) return;

    e.stopPropagation();

    switch (action) {
      case 'open':
        chrome.tabs.create({ url: bookmark.url });
        break;
      case 'edit':
        openEditModal(bookmark);
        break;
      case 'delete':
        deleteBookmark(id);
        break;
    }
  });
}

function openEditModal(bookmark) {
  document.getElementById('editId').value = bookmark.id;
  document.getElementById('editTitle').value = bookmark.title || '';
  document.getElementById('editUrl').value = bookmark.url || '';
  document.getElementById('editTags').value = (bookmark.tags || []).join(', ');
  document.getElementById('editDescription').value = bookmark.description || '';
  document.getElementById('editStars').checked = bookmark.stars || false;

  document.getElementById('editModal').classList.add('show');
}

function closeEditModal() {
  document.getElementById('editModal').classList.remove('show');
}

async function saveEdit(e) {
  e.preventDefault();

  const id = document.getElementById('editId').value;
  const data = {
    title: document.getElementById('editTitle').value,
    url: document.getElementById('editUrl').value,
    tags: document.getElementById('editTags').value
      .split(',')
      .map(t => t.trim())
      .filter(t => t),
    description: document.getElementById('editDescription').value || undefined,
    stars: document.getElementById('editStars').checked
  };

  try {
    const response = await fetch(`${serverUrl}/bookmarks/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });

    if (response.ok) {
      showNotification('Bookmark updated!', 'success');
      closeEditModal();
      await refreshData();

      // Refresh badge (in case stars changed)
      chrome.runtime.sendMessage({ type: 'refreshBadge' });
    } else {
      showNotification('Failed to update', 'error');
    }
  } catch (error) {
    console.error('saveEdit error:', error);
    showNotification('Save error: ' + error.message, 'error');
  }
}

async function addBookmark() {
  const tags = document.getElementById('bookmarkTags').value
    .split(',')
    .map(t => t.trim())
    .filter(t => t);
  const description = document.getElementById('bookmarkDescription').value.trim();
  const stars = document.getElementById('bookmarkStars').checked;

  const btn = document.getElementById('addBtn');
  btn.disabled = true;
  btn.textContent = 'Adding...';

  try {
    const response = await fetch(`${serverUrl}/bookmarks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: currentTab.url,
        title: currentTab.title,
        tags,
        description: description || undefined,
        stars
      })
    });

    if (response.ok) {
      const newBookmark = await response.json();
      showNotification('Bookmark added!', 'success');

      // Update local state immediately
      allBookmarks.push(newBookmark);
      existingBookmark = newBookmark;

      // Update UI to show "bookmarked" state
      checkBookmarkStatus();

      // Refresh badge
      chrome.runtime.sendMessage({ type: 'refreshBadge' });
    } else {
      const error = await response.json();
      showNotification(error.error || 'Failed to add', 'error');
    }
  } catch (error) {
    console.error('Add bookmark error:', error);
    showNotification('Failed to add bookmark', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Add Bookmark';
  }
}

async function trackVisit() {
  if (!existingBookmark) return;

  const btn = document.getElementById('visitBtn');
  btn.disabled = true;

  try {
    const response = await fetch(`${serverUrl}/bookmarks/${existingBookmark.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        visit_count: (existingBookmark.visit_count || 0) + 1,
        last_visited: new Date().toISOString()
      })
    });

    if (response.ok) {
      showNotification('Visit tracked!', 'success');
      await refreshData();
    } else {
      showNotification('Failed to track visit', 'error');
    }
  } catch (error) {
    console.error('trackVisit error:', error);
    showNotification('Track error: ' + error.message, 'error');
  } finally {
    btn.disabled = false;
  }
}

async function deleteBookmark(id) {
  if (!confirm('Delete this bookmark?')) return;

  try {
    const response = await fetch(`${serverUrl}/bookmarks/${id}`, {
      method: 'DELETE'
    });

    if (response.ok) {
      showNotification('Bookmark deleted', 'success');
      closeEditModal();
      await refreshData();

      // Refresh badge
      chrome.runtime.sendMessage({ type: 'refreshBadge' });
    } else {
      showNotification('Failed to delete', 'error');
    }
  } catch (error) {
    console.error('deleteBookmark error:', error);
    showNotification('Delete error: ' + error.message, 'error');
  }
}

async function refreshData() {
  try {
    // Load bookmarks first, then check status (which uses the local cache)
    await loadAllBookmarks();
    await checkBookmarkStatus();

    // Refresh current view
    const activeTab = document.querySelector('.tab.active');
    if (activeTab) {
      if (activeTab.dataset.tab === 'browse') {
        // Keep current browse state (view and filter)
        loadBrowseList();
      } else if (activeTab.dataset.tab === 'search') {
        const query = document.getElementById('searchInput').value;
        if (query) searchBookmarks(query);
      }
    }
  } catch (error) {
    console.error('refreshData error:', error);
  }
}

function getDomain(url) {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function showNotification(message, type) {
  const el = document.getElementById('notification');
  el.textContent = message;
  el.className = `notification ${type} show`;
  setTimeout(() => {
    el.classList.remove('show');
  }, 2000);
}
