// BTK Dashboard Application
const API_URL = 'http://localhost:8000';

// State
let bookmarks = [];
let tags = [];
let stats = {};
let currentTab = 'recent';
let activityChartInstance = null; // Store chart instance

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    feather.replace();
    loadDashboard();
    setupEventListeners();
});

// Setup event listeners
function setupEventListeners() {
    // Search
    document.getElementById('searchInput').addEventListener('input', (e) => {
        searchBookmarks(e.target.value);
    });

    // Add bookmark form
    document.getElementById('addBookmarkForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        await addBookmark(new FormData(e.target));
        hideAddModal();
        loadDashboard();
    });
}

// Load dashboard data
async function loadDashboard() {
    try {
        // Load bookmarks
        const bookmarksResponse = await fetch(`${API_URL}/bookmarks`);
        bookmarks = await bookmarksResponse.json();
        
        // Load stats
        const statsResponse = await fetch(`${API_URL}/stats`);
        stats = await statsResponse.json();
        
        // Load tags
        const tagsResponse = await fetch(`${API_URL}/tags?format=stats`);
        const tagStats = await tagsResponse.json();
        tags = Object.entries(tagStats).map(([tag, stat]) => ({
            name: tag,
            count: stat.bookmark_count
        }));
        
        // Update UI
        updateStats();
        updateBookmarksList();
        updateTagCloud();
        updateDomainStats();
        updateActivityChart();
        
    } catch (error) {
        console.error('Failed to load dashboard:', error);
        showNotification('Failed to load dashboard data', 'error');
    }
}

// Update statistics cards
function updateStats() {
    document.getElementById('totalBookmarks').textContent = stats.total_bookmarks || 0;
    document.getElementById('totalTags').textContent = stats.total_tags || 0;
    document.getElementById('starredCount').textContent = stats.starred_count || 0;
    document.getElementById('duplicateCount').textContent = stats.duplicate_count || 0;
}

// Update bookmarks list
function updateBookmarksList() {
    const container = document.getElementById('bookmarksContainer');
    let filteredBookmarks = bookmarks;
    
    // Filter based on current tab
    if (currentTab === 'starred') {
        filteredBookmarks = bookmarks.filter(b => b.stars);
    } else if (currentTab === 'unvisited') {
        filteredBookmarks = bookmarks.filter(b => b.visit_count === 0);
    } else {
        // Recent - sort by added date
        filteredBookmarks = [...bookmarks].sort((a, b) => 
            new Date(b.added) - new Date(a.added)
        );
    }
    
    // Limit to 20 bookmarks
    filteredBookmarks = filteredBookmarks.slice(0, 20);
    
    if (filteredBookmarks.length === 0) {
        container.innerHTML = '<p class="text-gray-500 text-center py-8">No bookmarks found</p>';
        return;
    }
    
    container.innerHTML = filteredBookmarks.map(bookmark => `
        <div class="bookmark-card bg-gray-50 rounded-lg p-4 hover:bg-gray-100">
            <div class="flex items-start justify-between">
                <div class="flex-1">
                    <h4 class="font-medium text-gray-800 mb-1">
                        ${bookmark.stars ? '<i data-feather="star" class="inline w-4 h-4 text-yellow-500 mr-1"></i>' : ''}
                        ${escapeHtml(bookmark.title)}
                    </h4>
                    <a href="${escapeHtml(bookmark.url)}" target="_blank" 
                       class="text-sm text-indigo-600 hover:text-indigo-800 break-all">
                        ${escapeHtml(bookmark.url)}
                    </a>
                    ${bookmark.description ? `
                        <p class="text-sm text-gray-600 mt-1">${escapeHtml(bookmark.description)}</p>
                    ` : ''}
                    <div class="flex items-center gap-4 mt-2">
                        ${bookmark.tags && bookmark.tags.length > 0 ? `
                            <div class="flex flex-wrap gap-1">
                                ${bookmark.tags.map(tag => `
                                    <span class="px-2 py-0.5 bg-indigo-100 text-indigo-700 text-xs rounded">
                                        ${escapeHtml(tag)}
                                    </span>
                                `).join('')}
                            </div>
                        ` : ''}
                        <span class="text-xs text-gray-500">
                            ${bookmark.visit_count} visits
                        </span>
                    </div>
                </div>
                <div class="flex gap-2 ml-4">
                    <button onclick="editBookmark(${bookmark.id})" 
                            class="text-gray-400 hover:text-gray-600">
                        <i data-feather="edit-2" class="w-4 h-4"></i>
                    </button>
                    <button onclick="deleteBookmark(${bookmark.id})" 
                            class="text-gray-400 hover:text-red-600">
                        <i data-feather="trash-2" class="w-4 h-4"></i>
                    </button>
                </div>
            </div>
        </div>
    `).join('');
    
    // Re-render feather icons
    feather.replace();
}

// Update tag cloud
function updateTagCloud() {
    const container = document.getElementById('tagCloud');
    
    // Sort tags by count and take top 20
    const topTags = tags.sort((a, b) => b.count - a.count).slice(0, 20);
    
    if (topTags.length === 0) {
        container.innerHTML = '<p class="text-gray-500 text-center">No tags yet</p>';
        return;
    }
    
    // Calculate font sizes based on count
    const maxCount = Math.max(...topTags.map(t => t.count));
    const minCount = Math.min(...topTags.map(t => t.count));
    
    container.innerHTML = topTags.map(tag => {
        const size = calculateTagSize(tag.count, minCount, maxCount);
        return `
            <span class="inline-block px-3 py-1 m-1 bg-indigo-50 text-indigo-700 rounded-full cursor-pointer hover:bg-indigo-100"
                  style="font-size: ${size}px"
                  onclick="filterByTag('${escapeHtml(tag.name)}')">
                ${escapeHtml(tag.name)} (${tag.count})
            </span>
        `;
    }).join('');
}

// Update domain statistics
function updateDomainStats() {
    const container = document.getElementById('domainStats');
    
    // Count bookmarks per domain
    const domainCounts = {};
    bookmarks.forEach(bookmark => {
        try {
            const url = new URL(bookmark.url);
            const domain = url.hostname;
            domainCounts[domain] = (domainCounts[domain] || 0) + 1;
        } catch (e) {
            // Invalid URL
        }
    });
    
    // Sort and take top 5
    const topDomains = Object.entries(domainCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5);
    
    if (topDomains.length === 0) {
        container.innerHTML = '<p class="text-gray-500 text-center">No domains yet</p>';
        return;
    }
    
    const maxCount = topDomains[0][1];
    
    container.innerHTML = topDomains.map(([domain, count]) => `
        <div class="flex items-center justify-between py-2">
            <span class="text-sm text-gray-700">${escapeHtml(domain)}</span>
            <div class="flex items-center gap-2">
                <div class="w-24 bg-gray-200 rounded-full h-2">
                    <div class="bg-indigo-600 h-2 rounded-full" 
                         style="width: ${(count / maxCount) * 100}%"></div>
                </div>
                <span class="text-sm text-gray-600 w-8 text-right">${count}</span>
            </div>
        </div>
    `).join('');
}

// Update activity chart
function updateActivityChart() {
    const ctx = document.getElementById('activityChart').getContext('2d');
    
    // Destroy existing chart instance if it exists
    if (activityChartInstance) {
        activityChartInstance.destroy();
    }
    
    // Group bookmarks by month
    const monthCounts = {};
    const now = new Date();
    
    // Initialize last 6 months
    for (let i = 5; i >= 0; i--) {
        const date = new Date(now.getFullYear(), now.getMonth() - i, 1);
        const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
        monthCounts[key] = 0;
    }
    
    // Count bookmarks
    bookmarks.forEach(bookmark => {
        if (bookmark.added) {
            const date = new Date(bookmark.added);
            const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
            if (monthCounts.hasOwnProperty(key)) {
                monthCounts[key]++;
            }
        }
    });
    
    const labels = Object.keys(monthCounts).map(key => {
        const [year, month] = key.split('-');
        return new Date(year, month - 1).toLocaleDateString('en', { month: 'short' });
    });
    
    activityChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Bookmarks Added',
                data: Object.values(monthCounts),
                borderColor: 'rgb(99, 102, 241)',
                backgroundColor: 'rgba(99, 102, 241, 0.1)',
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        precision: 0
                    }
                }
            }
        }
    });
}

// Tab switching
function switchTab(tab) {
    currentTab = tab;
    
    // Update tab styles
    document.querySelectorAll('.tab-btn').forEach(btn => {
        if (btn.dataset.tab === tab) {
            btn.className = 'tab-btn px-6 py-3 text-sm font-medium text-indigo-600 border-b-2 border-indigo-600';
        } else {
            btn.className = 'tab-btn px-6 py-3 text-sm font-medium text-gray-500 hover:text-gray-700';
        }
    });
    
    updateBookmarksList();
}

// Search bookmarks
async function searchBookmarks(query) {
    if (!query) {
        updateBookmarksList();
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, limit: 20 })
        });
        
        const results = await response.json();
        
        // Update bookmarks list with search results
        const container = document.getElementById('bookmarksContainer');
        container.innerHTML = results.map(bookmark => `
            <!-- Same bookmark card HTML as in updateBookmarksList -->
        `).join('');
        
        feather.replace();
    } catch (error) {
        console.error('Search failed:', error);
    }
}

// Add bookmark
async function addBookmark(formData) {
    const bookmark = {
        url: formData.get('url'),
        title: formData.get('title'),
        tags: formData.get('tags').split(',').map(t => t.trim()).filter(t => t),
        description: formData.get('description'),
        stars: formData.get('stars') === 'on'
    };
    
    try {
        const response = await fetch(`${API_URL}/bookmarks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bookmark)
        });
        
        if (response.ok) {
            showNotification('Bookmark added successfully', 'success');
        } else {
            const error = await response.json();
            showNotification(error.detail || 'Failed to add bookmark', 'error');
        }
    } catch (error) {
        console.error('Failed to add bookmark:', error);
        showNotification('Failed to add bookmark', 'error');
    }
}

// Delete bookmark
async function deleteBookmark(id) {
    if (!confirm('Are you sure you want to delete this bookmark?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/bookmarks/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification('Bookmark deleted', 'success');
            loadDashboard();
        }
    } catch (error) {
        console.error('Failed to delete bookmark:', error);
        showNotification('Failed to delete bookmark', 'error');
    }
}

// Export bookmarks
async function exportBookmarks(format) {
    try {
        const response = await fetch(`${API_URL}/export/${format}`);
        const blob = await response.blob();
        
        // Create download link
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `bookmarks.${format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        showNotification(`Exported as ${format.toUpperCase()}`, 'success');
    } catch (error) {
        console.error('Export failed:', error);
        showNotification('Export failed', 'error');
    }
}

// Filter by tag
function filterByTag(tag) {
    document.getElementById('searchInput').value = `tag:${tag}`;
    searchBookmarks(`tag:${tag}`);
}

// Refresh data
function refreshData() {
    loadDashboard();
    showNotification('Dashboard refreshed', 'success');
}

// Modal functions
function showAddModal() {
    document.getElementById('addModal').classList.remove('hidden');
}

function hideAddModal() {
    document.getElementById('addModal').classList.add('hidden');
    document.getElementById('addBookmarkForm').reset();
}

function showDedupeModal() {
    // TODO: Implement deduplication modal
    alert('Deduplication feature coming soon!');
}

function showImportModal() {
    // TODO: Implement import modal
    alert('Import feature coming soon!');
}

// Utility functions
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function calculateTagSize(count, min, max) {
    const minSize = 12;
    const maxSize = 24;
    if (max === min) return minSize;
    return minSize + ((count - min) / (max - min)) * (maxSize - minSize);
}

function showNotification(message, type = 'info') {
    // Simple notification (could be replaced with a toast library)
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 px-6 py-3 rounded-lg text-white z-50 ${
        type === 'success' ? 'bg-green-500' : 
        type === 'error' ? 'bg-red-500' : 
        'bg-blue-500'
    }`;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 3000);
}