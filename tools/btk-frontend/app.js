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
const PAGE_SIZE = 50;

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
function applyFilters() {
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
        const query = searchQuery.toLowerCase();
        results = results.filter(b =>
            (b.title && b.title.toLowerCase().includes(query)) ||
            (b.url && b.url.toLowerCase().includes(query)) ||
            (b.description && b.description.toLowerCase().includes(query)) ||
            (b.tags && b.tags.some(t => t.toLowerCase().includes(query)))
        );
    }

    // Apply sort
    results = sortBookmarks(results);

    filteredBookmarks = results;
    updateDisplay();
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
    applyFilters();
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
