// BTK Frontend Application
const API_URL = window.location.origin;

// State
let allBookmarks = [];
let filteredBookmarks = [];
let tags = [];
let currentFilter = 'all';
let currentTag = null;
let currentSort = 'added_desc';
let currentView = 'list';
let currentPage = 1;
let searchQuery = '';
let useFTS = false;  // Full-text search toggle
let ftsResults = null;  // Cache FTS results
const PAGE_SIZE = 50;

// Date view state
let dateViewData = null;
let dateNavigation = {
    year: null,
    month: null,
    day: null
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    feather.replace();
    loadData();
    setupEventListeners();
});

// Setup event listeners
function setupEventListeners() {
    // Search with debounce
    let searchTimeout;
    document.getElementById('searchInput').addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            searchQuery = e.target.value;
            currentPage = 1;
            applyFilters();
        }, 300);
    });

    // Add bookmark form
    document.getElementById('addBookmarkForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        await addBookmark(new FormData(e.target));
        hideAddModal();
        e.target.reset();
    });

    // Edit bookmark form
    document.getElementById('editBookmarkForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        await updateBookmark(new FormData(e.target));
        hideEditModal();
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            hideAddModal();
            hideEditModal();
        }
        if (e.key === '/' && !e.target.matches('input, textarea')) {
            e.preventDefault();
            document.getElementById('searchInput').focus();
        }
    });
}

// Load all data
async function loadData() {
    try {
        const [bookmarksRes, tagsRes, statsRes] = await Promise.all([
            fetch(`${API_URL}/bookmarks?limit=10000`),
            fetch(`${API_URL}/tags?format=stats`),
            fetch(`${API_URL}/stats`)
        ]);

        allBookmarks = await bookmarksRes.json();
        const tagStats = await tagsRes.json();
        const stats = await statsRes.json();

        // Convert tag stats to array
        tags = Object.entries(tagStats).map(([name, stat]) => ({
            name,
            count: stat.bookmark_count
        })).sort((a, b) => b.count - a.count);

        // Update UI
        document.getElementById('totalCount').textContent = stats.total_bookmarks || allBookmarks.length;
        updateTagList();
        applyFilters();

    } catch (error) {
        console.error('Failed to load data:', error);
        showNotification('Failed to load bookmarks', 'error');
    }
}

// Update tag list in sidebar
function updateTagList() {
    const container = document.getElementById('tagList');

    if (tags.length === 0) {
        container.innerHTML = '<p class="text-gray-400 text-sm px-3">No tags</p>';
        return;
    }

    container.innerHTML = tags.slice(0, 50).map(tag => `
        <button onclick="setTagFilter('${escapeHtml(tag.name)}')"
                class="tag-item w-full text-left px-3 py-1.5 rounded text-sm flex items-center justify-between ${currentTag === tag.name ? 'active' : ''}"
                data-tag="${escapeHtml(tag.name)}">
            <span class="truncate">${escapeHtml(tag.name)}</span>
            <span class="text-gray-400 text-xs">${tag.count}</span>
        </button>
    `).join('');
}

// Apply filters and update display
async function applyFilters() {
    let results = [...allBookmarks];

    // Apply quick filter
    if (currentFilter === 'starred') {
        results = results.filter(b => b.stars);
    } else if (currentFilter === 'unread') {
        results = results.filter(b => b.visit_count === 0);
    } else if (currentFilter === 'recent') {
        const weekAgo = new Date();
        weekAgo.setDate(weekAgo.getDate() - 7);
        results = results.filter(b => new Date(b.added) > weekAgo);
    }

    // Apply tag filter
    if (currentTag) {
        results = results.filter(b => b.tags && b.tags.includes(currentTag));
    }

    // Apply search
    if (searchQuery) {
        if (useFTS) {
            // Use FTS search with server
            try {
                const ftsData = await performFTSSearch(searchQuery);
                ftsResults = ftsData;
                // Create result list from FTS results
                results = ftsData.map(r => ({
                    ...r.bookmark,
                    _rank: r.rank,
                    _snippet: r.snippet
                }));
                // Apply other filters on top of FTS results
                if (currentFilter === 'starred') {
                    results = results.filter(b => b.stars);
                } else if (currentFilter === 'unread') {
                    results = results.filter(b => b.visit_count === 0);
                }
                if (currentTag) {
                    results = results.filter(b => b.tags && b.tags.includes(currentTag));
                }
            } catch (err) {
                console.error('FTS search failed:', err);
                showNotification('FTS search failed, using local search', 'warning');
                // Fall back to local search
                const query = searchQuery.toLowerCase();
                results = results.filter(b =>
                    (b.title && b.title.toLowerCase().includes(query)) ||
                    (b.url && b.url.toLowerCase().includes(query)) ||
                    (b.description && b.description.toLowerCase().includes(query)) ||
                    (b.tags && b.tags.some(t => t.toLowerCase().includes(query)))
                );
            }
        } else {
            // Local search
            const query = searchQuery.toLowerCase();
            results = results.filter(b =>
                (b.title && b.title.toLowerCase().includes(query)) ||
                (b.url && b.url.toLowerCase().includes(query)) ||
                (b.description && b.description.toLowerCase().includes(query)) ||
                (b.tags && b.tags.some(t => t.toLowerCase().includes(query)))
            );
            ftsResults = null;
        }
    } else {
        ftsResults = null;
    }

    // Apply sort (skip if FTS since results are ranked)
    if (!useFTS || !searchQuery) {
        results = sortBookmarks(results);
    }

    filteredBookmarks = results;
    updateDisplay();
}

// Toggle FTS search mode
function toggleFTS() {
    useFTS = !useFTS;
    const btn = document.getElementById('ftsToggle');
    if (useFTS) {
        btn.classList.add('bg-indigo-600', 'text-white');
        btn.classList.remove('hover:bg-gray-100');
        document.getElementById('searchInput').placeholder = 'Full-text search...';
    } else {
        btn.classList.remove('bg-indigo-600', 'text-white');
        btn.classList.add('hover:bg-gray-100');
        document.getElementById('searchInput').placeholder = 'Search bookmarks...';
    }
    // Re-apply filters if there's a search query
    if (searchQuery) {
        currentPage = 1;
        applyFilters();
    }
}

// Perform FTS search via API
async function performFTSSearch(query) {
    const response = await fetch(`${API_URL}/fts/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, limit: 100 })
    });
    if (!response.ok) {
        throw new Error(`FTS search failed: ${response.status}`);
    }
    return response.json();
}

// Sort bookmarks
function sortBookmarks(bookmarks) {
    const [field, direction] = currentSort.split('_');
    const mult = direction === 'desc' ? -1 : 1;

    return bookmarks.sort((a, b) => {
        if (field === 'added') {
            return mult * (new Date(a.added) - new Date(b.added));
        } else if (field === 'title') {
            return mult * (a.title || '').localeCompare(b.title || '');
        } else if (field === 'visits') {
            return mult * ((a.visit_count || 0) - (b.visit_count || 0));
        }
        return 0;
    });
}

// Update display
function updateDisplay() {
    updateFilterLabel();
    updateBookmarksList();
    updatePagination();
    feather.replace();
}

// Update filter label
function updateFilterLabel() {
    let label = 'All Bookmarks';
    if (currentFilter === 'starred') label = 'Starred';
    else if (currentFilter === 'unread') label = 'Unread';
    else if (currentFilter === 'recent') label = 'Recent (7 days)';
    else if (currentFilter === 'bydate') {
        const field = document.getElementById('dateField')?.value || 'added';
        const months = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        let datePath = field === 'added' ? 'Added' : 'Visited';
        if (dateNavigation.year) datePath += `: ${dateNavigation.year}`;
        if (dateNavigation.month) datePath += ` ${months[dateNavigation.month]}`;
        if (dateNavigation.day) datePath += ` ${dateNavigation.day}`;
        label = datePath;
    }

    if (currentTag) {
        label = `Tag: ${currentTag}`;
    }

    if (searchQuery) {
        label = `Search: "${searchQuery}"`;
    }

    document.getElementById('currentFilter').textContent = label;
    document.getElementById('resultCount').textContent = `(${filteredBookmarks.length})`;

    // Update active states
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.toggle('bg-indigo-100', btn.dataset.filter === currentFilter && !currentTag);
        btn.classList.toggle('text-indigo-700', btn.dataset.filter === currentFilter && !currentTag);
    });

    document.querySelectorAll('.tag-item').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tag === currentTag);
    });
}

// Update bookmarks list
function updateBookmarksList() {
    const container = document.getElementById('bookmarksContainer');
    const start = (currentPage - 1) * PAGE_SIZE;
    const pageBookmarks = filteredBookmarks.slice(start, start + PAGE_SIZE);

    if (pageBookmarks.length === 0) {
        container.innerHTML = '<p class="text-gray-500 text-center py-12">No bookmarks found</p>';
        return;
    }

    if (currentView === 'grid') {
        container.className = 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4';
        container.innerHTML = pageBookmarks.map(b => renderBookmarkCard(b, 'grid')).join('');
    } else {
        container.className = 'space-y-2';
        container.innerHTML = pageBookmarks.map(b => renderBookmarkCard(b, 'list')).join('');
    }
}

// Render bookmark card
function renderBookmarkCard(bookmark, view) {
    const domain = getDomain(bookmark.url);
    const favicon = `https://www.google.com/s2/favicons?domain=${domain}&sz=32`;

    if (view === 'grid') {
        return `
            <div class="bookmark-card bg-white rounded-lg p-4 border transition-all">
                <div class="flex items-start gap-3">
                    <img src="${favicon}" class="w-6 h-6 rounded mt-0.5" onerror="this.style.display='none'">
                    <div class="flex-1 min-w-0">
                        <h4 class="font-medium text-gray-800 truncate">
                            ${bookmark.stars ? '<i data-feather="star" class="inline w-3 h-3 text-yellow-500 mr-1"></i>' : ''}
                            ${escapeHtml(bookmark.title || bookmark.url)}
                        </h4>
                        <a href="${escapeHtml(bookmark.url)}" target="_blank"
                           class="text-xs text-indigo-600 hover:underline truncate block">${escapeHtml(domain)}</a>
                    </div>
                </div>
                ${bookmark.tags && bookmark.tags.length > 0 ? `
                    <div class="flex flex-wrap gap-1 mt-3">
                        ${bookmark.tags.slice(0, 3).map(tag => `
                            <span onclick="setTagFilter('${escapeHtml(tag)}')"
                                  class="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded cursor-pointer hover:bg-indigo-100">
                                ${escapeHtml(tag)}
                            </span>
                        `).join('')}
                        ${bookmark.tags.length > 3 ? `<span class="text-xs text-gray-400">+${bookmark.tags.length - 3}</span>` : ''}
                    </div>
                ` : ''}
                <div class="flex items-center justify-between mt-3 pt-3 border-t">
                    <span class="text-xs text-gray-400">${formatDate(bookmark.added)}</span>
                    <div class="flex gap-1">
                        <button onclick="editBookmark(${bookmark.id})" class="p-1 text-gray-400 hover:text-gray-600">
                            <i data-feather="edit-2" class="w-3.5 h-3.5"></i>
                        </button>
                        <button onclick="deleteBookmark(${bookmark.id})" class="p-1 text-gray-400 hover:text-red-600">
                            <i data-feather="trash-2" class="w-3.5 h-3.5"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    // List view
    return `
        <div class="bookmark-card bg-white rounded-lg px-4 py-3 border transition-all flex items-center gap-4">
            <img src="${favicon}" class="w-5 h-5 rounded flex-shrink-0" onerror="this.style.display='none'">
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                    ${bookmark.stars ? '<i data-feather="star" class="w-3.5 h-3.5 text-yellow-500 flex-shrink-0"></i>' : ''}
                    <a href="${escapeHtml(bookmark.url)}" target="_blank"
                       class="font-medium text-gray-800 hover:text-indigo-600 truncate">
                        ${escapeHtml(bookmark.title || bookmark.url)}
                    </a>
                    <span class="text-xs text-gray-400 flex-shrink-0">${escapeHtml(domain)}</span>
                </div>
                ${bookmark.tags && bookmark.tags.length > 0 ? `
                    <div class="flex flex-wrap gap-1 mt-1">
                        ${bookmark.tags.map(tag => `
                            <span onclick="setTagFilter('${escapeHtml(tag)}')"
                                  class="px-1.5 py-0.5 bg-gray-100 text-gray-600 text-xs rounded cursor-pointer hover:bg-indigo-100">
                                ${escapeHtml(tag)}
                            </span>
                        `).join('')}
                    </div>
                ` : ''}
            </div>
            <div class="flex items-center gap-3 flex-shrink-0">
                <span class="text-xs text-gray-400">${formatDate(bookmark.added)}</span>
                <span class="text-xs text-gray-400" title="Visits">${bookmark.visit_count || 0}</span>
                <button onclick="editBookmark(${bookmark.id})" class="p-1 text-gray-400 hover:text-gray-600">
                    <i data-feather="edit-2" class="w-4 h-4"></i>
                </button>
                <button onclick="deleteBookmark(${bookmark.id})" class="p-1 text-gray-400 hover:text-red-600">
                    <i data-feather="trash-2" class="w-4 h-4"></i>
                </button>
            </div>
        </div>
    `;
}

// Update pagination
function updatePagination() {
    const container = document.getElementById('pagination');
    const totalPages = Math.ceil(filteredBookmarks.length / PAGE_SIZE);

    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = '';

    // Previous button
    html += `<button onclick="goToPage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}
                     class="px-3 py-1.5 rounded border text-sm ${currentPage === 1 ? 'text-gray-300' : 'hover:bg-gray-100'}">
                <i data-feather="chevron-left" class="w-4 h-4"></i>
             </button>`;

    // Page numbers
    const pages = getPageNumbers(currentPage, totalPages);
    for (const page of pages) {
        if (page === '...') {
            html += '<span class="px-2 text-gray-400">...</span>';
        } else {
            html += `<button onclick="goToPage(${page})"
                             class="px-3 py-1.5 rounded text-sm ${page === currentPage ? 'bg-indigo-600 text-white' : 'border hover:bg-gray-100'}">
                        ${page}
                     </button>`;
        }
    }

    // Next button
    html += `<button onclick="goToPage(${currentPage + 1})" ${currentPage === totalPages ? 'disabled' : ''}
                     class="px-3 py-1.5 rounded border text-sm ${currentPage === totalPages ? 'text-gray-300' : 'hover:bg-gray-100'}">
                <i data-feather="chevron-right" class="w-4 h-4"></i>
             </button>`;

    container.innerHTML = html;
    feather.replace();
}

// Get page numbers to display
function getPageNumbers(current, total) {
    if (total <= 7) return Array.from({length: total}, (_, i) => i + 1);

    const pages = [];
    pages.push(1);

    if (current > 3) pages.push('...');

    for (let i = Math.max(2, current - 1); i <= Math.min(total - 1, current + 1); i++) {
        pages.push(i);
    }

    if (current < total - 2) pages.push('...');

    pages.push(total);
    return pages;
}

// Navigation functions
function goToPage(page) {
    const totalPages = Math.ceil(filteredBookmarks.length / PAGE_SIZE);
    if (page < 1 || page > totalPages) return;
    currentPage = page;
    updateDisplay();
    window.scrollTo(0, 0);
}

function setFilter(filter) {
    currentFilter = filter;
    currentTag = null;
    currentPage = 1;

    // Handle date view toggle
    if (filter === 'bydate') {
        showDateOptions(true);
    } else {
        showDateOptions(false);
        applyFilters();
    }
}

function setTagFilter(tag) {
    currentTag = tag === currentTag ? null : tag;
    currentFilter = 'all';
    currentPage = 1;
    applyFilters();
}

function handleSort() {
    currentSort = document.getElementById('sortSelect').value;
    applyFilters();
}

function setView(view) {
    currentView = view;
    document.getElementById('viewList').className = `px-3 py-1.5 text-sm rounded-l-lg ${view === 'list' ? 'bg-indigo-100 text-indigo-700' : 'hover:bg-gray-100'}`;
    document.getElementById('viewGrid').className = `px-3 py-1.5 text-sm rounded-r-lg ${view === 'grid' ? 'bg-indigo-100 text-indigo-700' : 'hover:bg-gray-100'}`;
    updateBookmarksList();
    feather.replace();
}

// CRUD operations
async function addBookmark(formData) {
    const bookmark = {
        url: formData.get('url'),
        title: formData.get('title') || undefined,
        tags: formData.get('tags') ? formData.get('tags').split(',').map(t => t.trim()).filter(t => t) : [],
        description: formData.get('description') || undefined,
        stars: formData.get('stars') === 'on'
    };

    try {
        const response = await fetch(`${API_URL}/bookmarks`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(bookmark)
        });

        if (response.ok) {
            showNotification('Bookmark added', 'success');
            loadData();
        } else {
            const error = await response.json();
            showNotification(error.error || 'Failed to add bookmark', 'error');
        }
    } catch (error) {
        console.error('Failed to add bookmark:', error);
        showNotification('Failed to add bookmark', 'error');
    }
}

async function editBookmark(id) {
    const bookmark = allBookmarks.find(b => b.id === id);
    if (!bookmark) return;

    document.getElementById('editId').value = id;
    document.getElementById('editUrl').value = bookmark.url;
    document.getElementById('editTitle').value = bookmark.title || '';
    document.getElementById('editTags').value = (bookmark.tags || []).join(', ');
    document.getElementById('editDescription').value = bookmark.description || '';
    document.getElementById('editStars').checked = bookmark.stars;

    document.getElementById('editModal').classList.remove('hidden');
}

async function updateBookmark(formData) {
    const id = formData.get('id');
    const data = {
        url: formData.get('url'),
        title: formData.get('title') || undefined,
        tags: formData.get('tags') ? formData.get('tags').split(',').map(t => t.trim()).filter(t => t) : [],
        description: formData.get('description') || undefined,
        stars: formData.get('stars') === 'on'
    };

    try {
        const response = await fetch(`${API_URL}/bookmarks/${id}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showNotification('Bookmark updated', 'success');
            loadData();
        } else {
            showNotification('Failed to update bookmark', 'error');
        }
    } catch (error) {
        console.error('Failed to update bookmark:', error);
        showNotification('Failed to update bookmark', 'error');
    }
}

async function deleteBookmark(id) {
    if (!confirm('Delete this bookmark?')) return;

    try {
        const response = await fetch(`${API_URL}/bookmarks/${id}`, {method: 'DELETE'});
        if (response.ok) {
            showNotification('Bookmark deleted', 'success');
            loadData();
        }
    } catch (error) {
        console.error('Failed to delete bookmark:', error);
        showNotification('Failed to delete bookmark', 'error');
    }
}

// Modal functions
function showAddModal() {
    document.getElementById('addModal').classList.remove('hidden');
    document.querySelector('#addBookmarkForm input[name="url"]').focus();
}

function hideAddModal() {
    document.getElementById('addModal').classList.add('hidden');
}

function hideEditModal() {
    document.getElementById('editModal').classList.add('hidden');
}

// Utility functions
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getDomain(url) {
    try {
        return new URL(url).hostname;
    } catch {
        return url;
    }
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays}d ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
    if (diffDays < 365) return `${Math.floor(diffDays / 30)}mo ago`;
    return date.toLocaleDateString();
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 px-4 py-2 rounded-lg text-white text-sm z-50 ${
        type === 'success' ? 'bg-green-500' :
        type === 'error' ? 'bg-red-500' :
        'bg-blue-500'
    }`;
    notification.textContent = message;
    document.body.appendChild(notification);
    setTimeout(() => notification.remove(), 3000);
}

// Export functions
function toggleExportMenu() {
    const menu = document.getElementById('exportMenu');
    menu.classList.toggle('hidden');

    // Close menu when clicking outside
    const closeMenu = (e) => {
        if (!e.target.closest('#exportMenu') && !e.target.closest('[onclick*="toggleExportMenu"]')) {
            menu.classList.add('hidden');
            document.removeEventListener('click', closeMenu);
        }
    };

    if (!menu.classList.contains('hidden')) {
        setTimeout(() => document.addEventListener('click', closeMenu), 0);
    }
}

function exportFiltered(format) {
    toggleExportMenu(); // Close the menu

    if (filteredBookmarks.length === 0) {
        showNotification('No bookmarks to export', 'error');
        return;
    }

    let content, filename, mimeType;

    switch (format) {
        case 'json':
            content = JSON.stringify(filteredBookmarks, null, 2);
            filename = 'bookmarks.json';
            mimeType = 'application/json';
            break;

        case 'csv':
            content = exportToCSV(filteredBookmarks);
            filename = 'bookmarks.csv';
            mimeType = 'text/csv';
            break;

        case 'html':
            content = exportToNetscapeHTML(filteredBookmarks);
            filename = 'bookmarks.html';
            mimeType = 'text/html';
            break;

        case 'markdown':
            content = exportToMarkdown(filteredBookmarks);
            filename = 'bookmarks.md';
            mimeType = 'text/markdown';
            break;

        default:
            showNotification('Unknown format', 'error');
            return;
    }

    // Download the file
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showNotification(`Exported ${filteredBookmarks.length} bookmarks as ${format.toUpperCase()}`, 'success');
}

function exportToCSV(bookmarks) {
    const headers = ['id', 'url', 'title', 'description', 'tags', 'added', 'stars', 'visit_count'];
    const rows = [headers.join(',')];

    for (const b of bookmarks) {
        const row = [
            b.id,
            `"${(b.url || '').replace(/"/g, '""')}"`,
            `"${(b.title || '').replace(/"/g, '""')}"`,
            `"${(b.description || '').replace(/"/g, '""')}"`,
            `"${(b.tags || []).join(';')}"`,
            b.added || '',
            b.stars ? '1' : '0',
            b.visit_count || 0
        ];
        rows.push(row.join(','));
    }

    return rows.join('\n');
}

function exportToNetscapeHTML(bookmarks) {
    let html = `<!DOCTYPE NETSCAPE-Bookmark-file-1>
<!-- This is an automatically generated file.
     It will be read and overwritten.
     DO NOT EDIT! -->
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
`;

    for (const b of bookmarks) {
        const addDate = b.added ? Math.floor(new Date(b.added).getTime() / 1000) : '';
        const tags = (b.tags || []).join(',');
        html += `    <DT><A HREF="${escapeHtml(b.url)}" ADD_DATE="${addDate}"${tags ? ` TAGS="${escapeHtml(tags)}"` : ''}>${escapeHtml(b.title || b.url)}</A>\n`;
        if (b.description) {
            html += `    <DD>${escapeHtml(b.description)}\n`;
        }
    }

    html += `</DL><p>\n`;
    return html;
}

function exportToMarkdown(bookmarks) {
    let md = `# Bookmarks\n\nExported on ${new Date().toLocaleDateString()}\n\n`;

    // Group by tags
    const byTag = {};
    const untagged = [];

    for (const b of bookmarks) {
        if (b.tags && b.tags.length > 0) {
            const tag = b.tags[0]; // Use first tag for grouping
            if (!byTag[tag]) byTag[tag] = [];
            byTag[tag].push(b);
        } else {
            untagged.push(b);
        }
    }

    // Output grouped bookmarks
    for (const tag of Object.keys(byTag).sort()) {
        md += `## ${tag}\n\n`;
        for (const b of byTag[tag]) {
            md += `- [${b.title || b.url}](${b.url})`;
            if (b.description) md += ` - ${b.description}`;
            md += '\n';
        }
        md += '\n';
    }

    if (untagged.length > 0) {
        md += `## Untagged\n\n`;
        for (const b of untagged) {
            md += `- [${b.title || b.url}](${b.url})`;
            if (b.description) md += ` - ${b.description}`;
            md += '\n';
        }
    }

    return md;
}

// Stats modal functions
function showStatsModal() {
    document.getElementById('statsModal').classList.remove('hidden');
    renderStats();
    feather.replace();
}

function hideStatsModal() {
    document.getElementById('statsModal').classList.add('hidden');
}

function renderStats() {
    const container = document.getElementById('statsContent');

    // Calculate stats from allBookmarks
    const totalBookmarks = allBookmarks.length;
    const starredCount = allBookmarks.filter(b => b.stars).length;
    const archivedCount = allBookmarks.filter(b => b.archived).length;
    const unreadCount = allBookmarks.filter(b => b.visit_count === 0).length;
    const totalVisits = allBookmarks.reduce((sum, b) => sum + (b.visit_count || 0), 0);

    // Domain stats
    const domainCounts = {};
    allBookmarks.forEach(b => {
        const domain = getDomain(b.url);
        domainCounts[domain] = (domainCounts[domain] || 0) + 1;
    });
    const topDomains = Object.entries(domainCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 10);

    // Tag stats (use already loaded tags)
    const topTags = tags.slice(0, 10);

    // Activity by month
    const monthCounts = {};
    allBookmarks.forEach(b => {
        if (b.added) {
            const date = new Date(b.added);
            const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
            monthCounts[key] = (monthCounts[key] || 0) + 1;
        }
    });
    const recentMonths = Object.entries(monthCounts)
        .sort((a, b) => b[0].localeCompare(a[0]))
        .slice(0, 6)
        .reverse();

    container.innerHTML = `
        <!-- Summary Cards -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="bg-indigo-50 rounded-lg p-4 text-center">
                <div class="text-2xl font-bold text-indigo-600">${totalBookmarks}</div>
                <div class="text-sm text-gray-600">Total Bookmarks</div>
            </div>
            <div class="bg-yellow-50 rounded-lg p-4 text-center">
                <div class="text-2xl font-bold text-yellow-600">${starredCount}</div>
                <div class="text-sm text-gray-600">Starred</div>
            </div>
            <div class="bg-gray-50 rounded-lg p-4 text-center">
                <div class="text-2xl font-bold text-gray-600">${unreadCount}</div>
                <div class="text-sm text-gray-600">Unread</div>
            </div>
            <div class="bg-green-50 rounded-lg p-4 text-center">
                <div class="text-2xl font-bold text-green-600">${totalVisits}</div>
                <div class="text-sm text-gray-600">Total Visits</div>
            </div>
        </div>

        <!-- Activity Chart -->
        <div class="bg-white border rounded-lg p-4">
            <h3 class="font-medium text-gray-800 mb-3">Activity (Last 6 Months)</h3>
            <div class="flex items-end gap-2 h-32">
                ${recentMonths.map(([month, count]) => {
                    const maxCount = Math.max(...recentMonths.map(r => r[1]));
                    const height = maxCount > 0 ? (count / maxCount) * 100 : 0;
                    return `
                        <div class="flex-1 flex flex-col items-center">
                            <div class="w-full bg-indigo-500 rounded-t" style="height: ${height}%"></div>
                            <div class="text-xs text-gray-500 mt-1">${month.slice(5)}</div>
                            <div class="text-xs text-gray-400">${count}</div>
                        </div>
                    `;
                }).join('')}
            </div>
        </div>

        <div class="grid md:grid-cols-2 gap-4">
            <!-- Top Domains -->
            <div class="bg-white border rounded-lg p-4">
                <h3 class="font-medium text-gray-800 mb-3">Top Domains</h3>
                <div class="space-y-2">
                    ${topDomains.map(([domain, count]) => `
                        <div class="flex items-center justify-between">
                            <span class="text-sm text-gray-600 truncate">${escapeHtml(domain)}</span>
                            <span class="text-sm text-gray-400">${count}</span>
                        </div>
                    `).join('')}
                    ${topDomains.length === 0 ? '<p class="text-sm text-gray-400">No bookmarks</p>' : ''}
                </div>
            </div>

            <!-- Top Tags -->
            <div class="bg-white border rounded-lg p-4">
                <h3 class="font-medium text-gray-800 mb-3">Top Tags</h3>
                <div class="space-y-2">
                    ${topTags.map(tag => `
                        <div class="flex items-center justify-between">
                            <span class="text-sm text-gray-600">${escapeHtml(tag.name)}</span>
                            <span class="text-sm text-gray-400">${tag.count}</span>
                        </div>
                    `).join('')}
                    ${topTags.length === 0 ? '<p class="text-sm text-gray-400">No tags</p>' : ''}
                </div>
            </div>
        </div>
    `;
}

// Import modal functions
function showImportModal() {
    document.getElementById('importModal').classList.remove('hidden');
    document.getElementById('importFile').value = '';
    feather.replace();
}

function hideImportModal() {
    document.getElementById('importModal').classList.add('hidden');
}

async function performImport() {
    const fileInput = document.getElementById('importFile');
    const file = fileInput.files[0];

    if (!file) {
        showNotification('Please select a file to import', 'error');
        return;
    }

    const reader = new FileReader();
    reader.onload = async (e) => {
        const content = e.target.result;
        const filename = file.name.toLowerCase();

        let format = 'html';
        if (filename.endsWith('.json')) format = 'json';
        else if (filename.endsWith('.csv')) format = 'csv';
        else if (filename.endsWith('.md')) format = 'markdown';
        else if (filename.endsWith('.txt')) format = 'text';

        try {
            const response = await fetch(`${API_URL}/import`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ content, format })
            });

            if (response.ok) {
                const result = await response.json();
                showNotification(`Imported ${result.imported || 0} bookmarks`, 'success');
                hideImportModal();
                loadData();
            } else {
                const error = await response.json();
                showNotification(error.error || 'Import failed', 'error');
            }
        } catch (error) {
            console.error('Import failed:', error);
            showNotification('Import failed: ' + error.message, 'error');
        }
    };

    reader.readAsText(file);
}

// Date View Functions
async function loadDateView() {
    const field = document.getElementById('dateField').value;
    const granularity = document.getElementById('dateGranularity').value;

    // Build query params based on navigation state
    let url = `${API_URL}/bookmarks/by-date?field=${field}&granularity=${granularity}`;
    if (dateNavigation.year) url += `&year=${dateNavigation.year}`;
    if (dateNavigation.month) url += `&month=${dateNavigation.month}`;
    if (dateNavigation.day) url += `&day=${dateNavigation.day}`;

    try {
        const response = await fetch(url);
        dateViewData = await response.json();
        renderDateGroups();
        updateDateBreadcrumb();

        // If we have specific filters, show the bookmarks
        if (dateNavigation.year || dateViewData.groups.length === 1) {
            // Get all bookmarks from the filtered groups
            filteredBookmarks = dateViewData.groups.flatMap(g => g.bookmarks);
            filteredBookmarks = sortBookmarks(filteredBookmarks);
            updateDisplay();
        }
    } catch (error) {
        console.error('Failed to load date view:', error);
        showNotification('Failed to load date view', 'error');
    }
}

function renderDateGroups() {
    const container = document.getElementById('dateGroups');
    const granularity = document.getElementById('dateGranularity').value;

    if (!dateViewData || dateViewData.groups.length === 0) {
        container.innerHTML = '<p class="text-gray-400 text-sm px-3">No bookmarks</p>';
        return;
    }

    container.innerHTML = dateViewData.groups.map(group => {
        const label = formatDateKey(group.key, granularity);
        return `
            <button onclick="navigateDateTo('${group.key}')"
                    class="date-group-item w-full text-left px-3 py-1.5 rounded text-sm flex items-center justify-between hover:bg-gray-100"
                    data-key="${group.key}">
                <span class="truncate">${escapeHtml(label)}</span>
                <span class="text-gray-400 text-xs">${group.count}</span>
            </button>
        `;
    }).join('');
}

function formatDateKey(key, granularity) {
    const parts = key.split('-');
    const months = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    if (granularity === 'year' || parts.length === 1) {
        return parts[0];
    } else if (granularity === 'month' || parts.length === 2) {
        return `${months[parseInt(parts[1])]} ${parts[0]}`;
    } else {
        return `${months[parseInt(parts[1])]} ${parseInt(parts[2])}, ${parts[0]}`;
    }
}

function navigateDateTo(key) {
    const parts = key.split('-');
    const granularity = document.getElementById('dateGranularity').value;

    if (parts.length === 1) {
        // Year selected
        dateNavigation.year = parseInt(parts[0]);
        dateNavigation.month = null;
        dateNavigation.day = null;
        // If granularity is year, show bookmarks; otherwise drill down to month
        if (granularity === 'year') {
            loadDateView();
        } else {
            // Change to month view for drill-down
            document.getElementById('dateGranularity').value = 'month';
            loadDateView();
        }
    } else if (parts.length === 2) {
        // Month selected
        dateNavigation.year = parseInt(parts[0]);
        dateNavigation.month = parseInt(parts[1]);
        dateNavigation.day = null;
        if (granularity === 'month') {
            loadDateView();
        } else {
            // Change to day view for drill-down
            document.getElementById('dateGranularity').value = 'day';
            loadDateView();
        }
    } else {
        // Day selected
        dateNavigation.year = parseInt(parts[0]);
        dateNavigation.month = parseInt(parts[1]);
        dateNavigation.day = parseInt(parts[2]);
        loadDateView();
    }
}

function navigateDateUp() {
    if (dateNavigation.day) {
        dateNavigation.day = null;
        document.getElementById('dateGranularity').value = 'month';
    } else if (dateNavigation.month) {
        dateNavigation.month = null;
        document.getElementById('dateGranularity').value = 'year';
    } else if (dateNavigation.year) {
        dateNavigation.year = null;
    }
    loadDateView();
}

function updateDateBreadcrumb() {
    const breadcrumb = document.getElementById('dateBreadcrumb');
    const months = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    if (dateNavigation.year || dateNavigation.month || dateNavigation.day) {
        let path = '';
        if (dateNavigation.year) path = dateNavigation.year;
        if (dateNavigation.month) path += ` / ${months[dateNavigation.month]}`;
        if (dateNavigation.day) path += ` / ${dateNavigation.day}`;

        breadcrumb.innerHTML = `
            <button onclick="navigateDateUp()" class="text-indigo-600 hover:underline flex items-center gap-1">
                <i data-feather="arrow-left" class="w-3 h-3"></i>
                Back
            </button>
            <span class="text-gray-600 mt-1 block">${path}</span>
        `;
        breadcrumb.classList.remove('hidden');
        feather.replace();
    } else {
        breadcrumb.classList.add('hidden');
    }
}

function handleDateOptionsChange() {
    // Reset navigation when options change
    dateNavigation = { year: null, month: null, day: null };
    loadDateView();
}

function showDateOptions(show) {
    const dateOptions = document.getElementById('dateOptions');
    if (show) {
        dateOptions.classList.remove('hidden');
        loadDateView();
    } else {
        dateOptions.classList.add('hidden');
        dateNavigation = { year: null, month: null, day: null };
    }
}
