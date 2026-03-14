/**
 * btk HTML-app JavaScript — sql.js query-driven rendering engine.
 *
 * Template variables WASM_URI and LOAD_MODE are set by the Python
 * template assembler before this script executes.
 *
 * WASM_URI  — URL or data URI for sql-wasm.wasm
 * LOAD_MODE — "embedded" (base64 DB in page) or "directory" (fetch export.db)
 */

/* global initSqlJs, WASM_URI, LOAD_MODE */

(async function () {
    "use strict";

    // ── Constants ─────────────────────────────────────────────────────

    var PAGE_SIZE = 50;

    var COLLECTIONS = {
        all:       { label: "All",       icon: "\u{1F4DA}", where: "1=1" },
        unread:    { label: "Unread",    icon: "\u{1F4D6}", where: "visit_count = 0" },
        starred:   { label: "Starred",   icon: "\u2B50",    where: "stars = 1" },
        pinned:    { label: "Pinned",    icon: "\u{1F4CC}", where: "pinned = 1" },
        archived:  { label: "Archived",  icon: "\u{1F4E6}", where: "archived = 1" },
        queue:     { label: "Queue",     icon: "\u{1F4DA}", where: "json_extract(extra_data, '$.reading_queue') = 1" },
        popular:   { label: "Popular",   icon: "\u{1F525}", where: "visit_count > 5", orderBy: "visit_count DESC", limit: 100 },
        media:     { label: "Media",     icon: "\u{1F3AC}", where: "id IN (SELECT bookmark_id FROM bookmark_media)" },
        broken:    { label: "Broken",    icon: "\u26A0\uFE0F",  where: "reachable = 0" },
        untagged:  { label: "Untagged",  icon: "\u{1F3F7}\uFE0F", where: "id NOT IN (SELECT bookmark_id FROM bookmark_tags)" },
        pdfs:      { label: "PDFs",      icon: "\u{1F4C4}", where: "url LIKE '%.pdf'" }
    };

    var SORT_OPTIONS = {
        "added-desc":   { col: "added",        dir: "DESC" },
        "added-asc":    { col: "added",        dir: "ASC" },
        "title-asc":    { col: "title",        dir: "ASC" },
        "title-desc":   { col: "title",        dir: "DESC" },
        "visits-desc":  { col: "visit_count",  dir: "DESC" },
        "visited-desc": { col: "last_visited", dir: "DESC" },
        "stars-desc":   { col: "stars",        dir: "DESC" }
    };

    var ALLOWED_QUERY_KEYWORDS = { SELECT: 1, WITH: 1, EXPLAIN: 1 };

    var SHORTCUTS = [
        { key: "/",   desc: "Focus search" },
        { key: "j",   desc: "Next bookmark" },
        { key: "k",   desc: "Previous bookmark" },
        { key: "g",   desc: "Grid view" },
        { key: "l",   desc: "List view" },
        { key: "t",   desc: "Table view" },
        { key: "m",   desc: "Gallery view" },
        { key: "d",   desc: "Toggle dark mode" },
        { key: "s",   desc: "Statistics" },
        { key: "q",   desc: "SQL query box" },
        { key: "?",   desc: "Show shortcuts" },
        { key: "Esc", desc: "Close modal" }
    ];

    // ── State ─────────────────────────────────────────────────────────

    var AppState = {
        db: null,
        sourceDbs: [],
        activeSourceDb: null,
        searchQuery: "",
        selectedTags: {},
        sortKey: "added-desc",
        activeCollection: "all",
        activeView: null,
        viewMode: "grid",
        theme: localStorage.getItem("btk-theme") || "light",
        page: 0,
        totalCount: 0,
        focusIndex: -1
    };

    // ── Helpers ────────────────────────────────────────────────────────

    /** Convert sql.js exec() result to array of row objects. */
    function execToRows(result) {
        if (!result || result.length === 0) return [];
        var cols = result[0].columns;
        var vals = result[0].values;
        var rows = [];
        for (var i = 0; i < vals.length; i++) {
            var row = {};
            for (var j = 0; j < cols.length; j++) {
                row[cols[j]] = vals[i][j];
            }
            rows.push(row);
        }
        return rows;
    }

    /** Run a query and return row objects. */
    function query(sql, params) {
        try {
            if (params) {
                var stmt = AppState.db.prepare(sql);
                stmt.bind(params);
                var rows = [];
                var cols = stmt.getColumnNames();
                while (stmt.step()) {
                    var vals = stmt.get();
                    var row = {};
                    for (var j = 0; j < cols.length; j++) {
                        row[cols[j]] = vals[j];
                    }
                    rows.push(row);
                }
                stmt.free();
                return rows;
            }
            return execToRows(AppState.db.exec(sql));
        } catch (e) {
            return [];
        }
    }

    /** Run a scalar query. */
    function scalar(sql) {
        var rows = query(sql);
        if (rows.length === 0) return 0;
        var keys = Object.keys(rows[0]);
        return rows[0][keys[0]];
    }

    /** Escape HTML to prevent XSS. */
    function esc(str) {
        if (str == null) return "";
        var d = document.createElement("div");
        d.appendChild(document.createTextNode(String(str)));
        return d.innerHTML;
    }

    /** Extract domain from URL. */
    function domain(url) {
        if (!url) return "";
        try {
            return new URL(url).hostname.replace(/^www\./, "");
        } catch (_) {
            return "";
        }
    }

    /** Format a date string for display. */
    function fmtDate(d) {
        if (!d) return "";
        try {
            var dt = new Date(d);
            if (isNaN(dt.getTime())) return String(d);
            return dt.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
        } catch (_) {
            return String(d);
        }
    }

    /** Convert favicon BLOB (Uint8Array) to data URI. Safe for large favicons. */
    function faviconDataUri(row) {
        if (!row.favicon_data) return null;
        var bytes = row.favicon_data;
        var mime = row.favicon_mime_type || "image/png";
        var binary = Array.from(bytes, function (b) { return String.fromCharCode(b); }).join("");
        return "data:" + mime + ";base64," + btoa(binary);
    }

    /** Render a favicon <img> or empty string. */
    function faviconImg(row, cls) {
        var uri = faviconDataUri(row);
        if (!uri) return "";
        return '<img src="' + esc(uri) + '" class="' + (cls || "favicon") + '" alt="" loading="lazy">';
    }

    /** Get tags for a bookmark by id. */
    function tagsForBookmark(bookmarkId) {
        return query(
            "SELECT t.name, t.color FROM tags t " +
            "JOIN bookmark_tags bt ON t.id = bt.tag_id " +
            "WHERE bt.bookmark_id = " + Number(bookmarkId)
        );
    }

    /** Get media for a bookmark by id. */
    function mediaForBookmark(bookmarkId) {
        var rows = query(
            "SELECT * FROM bookmark_media WHERE bookmark_id = " + Number(bookmarkId)
        );
        return rows.length > 0 ? rows[0] : null;
    }

    /** Get element by id (shorthand). */
    function $(id) { return document.getElementById(id); }

    // ── Query Builder ─────────────────────────────────────────────────

    function buildQuery(countOnly) {
        var col = COLLECTIONS[AppState.activeCollection] || COLLECTIONS.all;
        var wheres = [];
        var joins = [];
        var selectCols = countOnly ? "COUNT(*)" : "b.*";

        // Collection WHERE
        wheres.push(col.where);

        // Source DB filter
        if (AppState.activeSourceDb) {
            wheres.push("b.source_db = '" + AppState.activeSourceDb.replace(/'/g, "''") + "'");
        }

        // Tag filter
        var selTags = Object.keys(AppState.selectedTags);
        if (selTags.length > 0) {
            var tagNames = selTags.map(function (t) { return "'" + t.replace(/'/g, "''") + "'"; }).join(",");
            joins.push("JOIN bookmark_tags _bt ON b.id = _bt.bookmark_id");
            joins.push("JOIN tags _t ON _bt.tag_id = _t.id");
            wheres.push("_t.name IN (" + tagNames + ")");
        }

        // Search
        if (AppState.searchQuery) {
            var q = "%" + AppState.searchQuery.replace(/'/g, "''") + "%";
            wheres.push("(b.title LIKE '" + q + "' OR b.url LIKE '" + q + "' OR b.description LIKE '" + q + "')");
        }

        // Starred / Pinned filter checkboxes
        var starredCheck = $("filter-starred");
        if (starredCheck && starredCheck.checked) {
            wheres.push("b.stars = 1");
        }
        var pinnedCheck = $("filter-pinned");
        if (pinnedCheck && pinnedCheck.checked) {
            wheres.push("b.pinned = 1");
        }

        // View filter (bookmark IDs)
        if (AppState.activeView) {
            var viewData = getViewsData();
            var view = viewData[AppState.activeView];
            if (view && view.bookmark_ids && view.bookmark_ids.length > 0) {
                wheres.push("b.id IN (" + view.bookmark_ids.join(",") + ")");
            }
        }

        var sql = "SELECT " + selectCols + " FROM bookmarks b";
        if (joins.length > 0) {
            sql += " " + joins.join(" ");
        }
        sql += " WHERE " + wheres.join(" AND ");

        if (selTags.length > 0 && !countOnly) {
            sql += " GROUP BY b.id";
        }

        if (!countOnly) {
            // ORDER BY
            var orderBy = col.orderBy || null;
            if (!orderBy) {
                var sort = SORT_OPTIONS[AppState.sortKey] || SORT_OPTIONS["added-desc"];
                orderBy = sort.col + " " + sort.dir;
            }
            sql += " ORDER BY " + orderBy;

            // LIMIT / OFFSET
            var limit = col.limit || PAGE_SIZE;
            var offset = AppState.page * PAGE_SIZE;
            sql += " LIMIT " + limit + " OFFSET " + offset;
        }

        return sql;
    }

    function buildCountQuery() {
        return buildQuery(true);
    }

    // ── Views Data ────────────────────────────────────────────────────

    function getViewsData() {
        try {
            var el = $("btk-views");
            if (!el) return {};
            return JSON.parse(el.textContent || "{}");
        } catch (_) {
            return {};
        }
    }

    // ── Rendering ─────────────────────────────────────────────────────

    function render() {
        var countSql = buildCountQuery();
        AppState.totalCount = scalar(countSql);

        var sql = buildQuery(false);
        var bookmarks = query(sql);

        renderBookmarkCount();
        renderBookmarks(bookmarks);
        renderPagination();
        AppState.focusIndex = -1;
    }

    function renderBookmarkCount() {
        var el = $("bookmark-count");
        if (el) {
            el.textContent = AppState.totalCount + " bookmark" + (AppState.totalCount !== 1 ? "s" : "");
        }
    }

    function renderBookmarks(bookmarks) {
        var container = $("bookmark-list");
        if (!container) return;

        if (bookmarks.length === 0) {
            container.innerHTML =
                '<div class="empty-state">' +
                '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">' +
                '<path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>' +
                '</svg>' +
                '<h3>No bookmarks found</h3>' +
                '<p>Try adjusting your search or filters.</p></div>';
            return;
        }

        var mode = AppState.viewMode;
        var html = "";

        if (mode === "table") {
            html = renderTable(bookmarks);
        } else {
            for (var i = 0; i < bookmarks.length; i++) {
                var b = bookmarks[i];
                var tags = tagsForBookmark(b.id);
                if (mode === "grid") {
                    html += renderCard(b, tags, i);
                } else if (mode === "list") {
                    html += renderListItem(b, tags, i);
                } else if (mode === "gallery") {
                    html += renderGalleryCard(b, i);
                }
            }
        }

        container.innerHTML = html;
        attachBookmarkListeners(container);
    }

    function renderCard(b, tags, idx) {
        var tagHtml = "";
        for (var i = 0; i < tags.length; i++) {
            var style = tags[i].color ? ' style="background:' + esc(tags[i].color) + '22;color:' + esc(tags[i].color) + '"' : "";
            tagHtml += '<span class="tag"' + style + '>' + esc(tags[i].name) + '</span>';
        }

        var media = mediaForBookmark(b.id);
        var badges = "";
        if (media) {
            badges += '<span class="badge badge-media">' + esc(media.media_type) + '</span>';
        }
        if (b.pinned) {
            badges += '<span class="badge badge-pinned">Pinned</span>';
        }

        return '<div class="bookmark-card" data-id="' + b.id + '" data-idx="' + idx + '" tabindex="0">' +
            '<div class="card-header">' +
                faviconImg(b) +
                '<h3 class="card-title">' + esc(b.title || b.url) + '</h3>' +
                (b.stars ? '<span class="card-star">\u2605</span>' : '') +
            '</div>' +
            '<a class="card-url" href="' + esc(b.url) + '" target="_blank" rel="noopener" onclick="event.stopPropagation()">' + esc(domain(b.url)) + '</a>' +
            (tagHtml ? '<div class="card-tags">' + tagHtml + '</div>' : '') +
            (badges ? '<div class="card-badges">' + badges + '</div>' : '') +
            '<div class="card-meta">' +
                '<span>' + esc(fmtDate(b.added)) + '</span>' +
                '<span>' + (b.visit_count || 0) + ' visits</span>' +
            '</div>' +
        '</div>';
    }

    function renderListItem(b, tags, idx) {
        var tagHtml = "";
        for (var i = 0; i < Math.min(tags.length, 3); i++) {
            tagHtml += '<span class="tag">' + esc(tags[i].name) + '</span>';
        }

        return '<div class="bookmark-list-item" data-id="' + b.id + '" data-idx="' + idx + '" tabindex="0">' +
            faviconImg(b, "list-favicon") +
            '<span class="list-title">' + esc(b.title || b.url) + '</span>' +
            '<span class="list-domain">' + esc(domain(b.url)) + '</span>' +
            '<div class="list-tags">' + tagHtml + '</div>' +
            '<div class="list-meta">' +
                (b.stars ? '<span class="list-star">\u2605</span>' : '') +
                '<span>' + esc(fmtDate(b.added)) + '</span>' +
            '</div>' +
        '</div>';
    }

    function renderTable(bookmarks) {
        var sort = SORT_OPTIONS[AppState.sortKey] || SORT_OPTIONS["added-desc"];
        var sortedCol = sort.col;
        var sortedDir = sort.dir.toLowerCase();

        var html = '<table class="bookmark-table"><thead><tr>';
        var cols = [
            { key: "title",       label: "Title" },
            { key: "url",         label: "Domain" },
            { key: "added",       label: "Added" },
            { key: "visit_count", label: "Visits" },
            { key: "stars",       label: "Stars" }
        ];
        for (var c = 0; c < cols.length; c++) {
            var cls = "";
            if (cols[c].key === sortedCol) {
                cls = ' class="sorted-' + sortedDir + '"';
            }
            html += '<th data-sort="' + cols[c].key + '"' + cls + '>' + cols[c].label + '</th>';
        }
        html += '</tr></thead><tbody>';

        for (var i = 0; i < bookmarks.length; i++) {
            var b = bookmarks[i];
            html += '<tr data-id="' + b.id + '" data-idx="' + i + '" tabindex="0">' +
                '<td><div class="table-title-cell">' +
                    faviconImg(b) +
                    '<span>' + esc(b.title || b.url) + '</span>' +
                '</div></td>' +
                '<td><a class="table-url" href="' + esc(b.url) + '" target="_blank" rel="noopener" onclick="event.stopPropagation()">' + esc(domain(b.url)) + '</a></td>' +
                '<td>' + esc(fmtDate(b.added)) + '</td>' +
                '<td>' + (b.visit_count || 0) + '</td>' +
                '<td>' + (b.stars ? '\u2605' : '') + '</td>' +
            '</tr>';
        }

        html += '</tbody></table>';
        return html;
    }

    function renderGalleryCard(b, idx) {
        var media = mediaForBookmark(b.id);
        var thumb = "";
        if (media && media.thumbnail_url) {
            thumb = '<img class="gallery-thumbnail" src="' + esc(media.thumbnail_url) + '" alt="" loading="lazy">';
        } else {
            var initial = (b.title || "?").charAt(0).toUpperCase();
            thumb = '<div class="gallery-placeholder">' + esc(initial) + '</div>';
        }

        var badge = "";
        if (media && media.media_type) {
            badge = '<div class="gallery-badge">' + esc(media.media_type) + '</div>';
        }

        var author = "";
        if (media && media.author_name) {
            author = '<div class="gallery-author">' + esc(media.author_name) + '</div>';
        }

        return '<div class="gallery-card" data-id="' + b.id + '" data-idx="' + idx + '" tabindex="0">' +
            thumb + badge +
            (media && media.media_type === "video" ? '<div class="play-button">\u25B6</div>' : '') +
            '<div class="gallery-overlay">' +
                '<div class="gallery-title">' + esc(b.title || b.url) + '</div>' +
                author +
            '</div>' +
        '</div>';
    }

    function attachBookmarkListeners(container) {
        var items = container.querySelectorAll("[data-id]");
        for (var i = 0; i < items.length; i++) {
            items[i].addEventListener("click", function (e) {
                if (e.target.tagName === "A") return;
                showBookmarkModal(Number(this.getAttribute("data-id")));
            });
        }
    }

    // ── Pagination ────────────────────────────────────────────────────

    function renderPagination() {
        var container = $("main-content");
        if (!container) return;

        var existing = container.querySelector(".pagination");
        if (existing) existing.remove();

        var totalPages = Math.ceil(AppState.totalCount / PAGE_SIZE);
        if (totalPages <= 1) return;

        var div = document.createElement("div");
        div.className = "pagination";
        div.style.cssText = "display:flex;justify-content:center;align-items:center;gap:1rem;padding:1.5rem 0;";

        var prevBtn = document.createElement("button");
        prevBtn.className = "btn btn-secondary";
        prevBtn.textContent = "Previous";
        prevBtn.disabled = AppState.page === 0;
        prevBtn.addEventListener("click", function () {
            if (AppState.page > 0) {
                AppState.page--;
                render();
                scrollToTop();
            }
        });

        var info = document.createElement("span");
        info.style.cssText = "color:var(--text-secondary);font-size:14px;";
        info.textContent = "Page " + (AppState.page + 1) + " of " + totalPages;

        var nextBtn = document.createElement("button");
        nextBtn.className = "btn btn-secondary";
        nextBtn.textContent = "Next";
        nextBtn.disabled = AppState.page >= totalPages - 1;
        nextBtn.addEventListener("click", function () {
            if (AppState.page < totalPages - 1) {
                AppState.page++;
                render();
                scrollToTop();
            }
        });

        div.appendChild(prevBtn);
        div.appendChild(info);
        div.appendChild(nextBtn);
        container.appendChild(div);
    }

    function scrollToTop() {
        var mc = $("main-content");
        if (mc) mc.scrollTop = 0;
    }

    // ── Tag Cloud ─────────────────────────────────────────────────────

    function renderTagCloud() {
        var el = $("tag-cloud");
        if (!el) return;

        var tags = query(
            "SELECT t.name, t.color, COUNT(*) AS c FROM tags t " +
            "JOIN bookmark_tags bt ON t.id = bt.tag_id " +
            "GROUP BY t.name ORDER BY c DESC"
        );

        var html = "";
        for (var i = 0; i < tags.length; i++) {
            var t = tags[i];
            var sel = AppState.selectedTags[t.name] ? " selected" : "";
            var style = t.color ? ' style="border-color:' + esc(t.color) + '"' : "";
            html += '<button class="tag-filter' + sel + '"' + style + ' data-tag="' + esc(t.name) + '">' +
                esc(t.name) + ' <span class="count">' + t.c + '</span></button>';
        }
        el.innerHTML = html;

        var buttons = el.querySelectorAll(".tag-filter");
        for (var j = 0; j < buttons.length; j++) {
            buttons[j].addEventListener("click", function () {
                var tag = this.getAttribute("data-tag");
                if (AppState.selectedTags[tag]) {
                    delete AppState.selectedTags[tag];
                } else {
                    AppState.selectedTags[tag] = true;
                }
                AppState.page = 0;
                renderTagCloud();
                render();
            });
        }
    }

    // ── Collections Sidebar ───────────────────────────────────────────

    function renderCollections() {
        var el = $("collections-list");
        if (!el) return;

        var html = '<div class="collections-list">';
        var keys = Object.keys(COLLECTIONS);
        for (var i = 0; i < keys.length; i++) {
            var key = keys[i];
            var col = COLLECTIONS[key];
            var count = scalar("SELECT COUNT(*) FROM bookmarks WHERE " + col.where);
            var active = AppState.activeCollection === key && !AppState.activeView ? " active" : "";
            html += '<div class="collection-item' + active + '" data-collection="' + key + '">' +
                '<span class="icon">' + col.icon + '</span>' +
                '<span class="name">' + esc(col.label) + '</span>' +
                '<span class="count">' + count + '</span>' +
            '</div>';
        }
        html += '</div>';
        el.innerHTML = html;

        var items = el.querySelectorAll(".collection-item");
        for (var j = 0; j < items.length; j++) {
            items[j].addEventListener("click", function () {
                AppState.activeCollection = this.getAttribute("data-collection");
                AppState.activeView = null;
                AppState.page = 0;
                renderCollections();
                renderViews();
                render();
            });
        }
    }

    // ── Views Sidebar ─────────────────────────────────────────────────

    function renderViews() {
        var section = $("views-section");
        var el = $("views-list");
        if (!section || !el) return;

        var viewsData = getViewsData();
        var keys = Object.keys(viewsData);
        if (keys.length === 0) {
            section.hidden = true;
            return;
        }
        section.hidden = false;

        var html = "";
        for (var i = 0; i < keys.length; i++) {
            var key = keys[i];
            var view = viewsData[key];
            var active = AppState.activeView === key ? " active" : "";
            var count = view.bookmark_ids ? view.bookmark_ids.length : 0;
            var desc = view.description || "";
            html += '<div class="view-item' + active + '" data-view="' + esc(key) + '">' +
                '<div class="view-header">' +
                    '<span class="view-name">' + esc(key) + '</span>' +
                    '<span class="view-count">' + count + '</span>' +
                '</div>' +
                (desc ? '<div class="view-description">' + esc(desc) + '</div>' : '') +
            '</div>';
        }
        el.innerHTML = html;

        var items = el.querySelectorAll(".view-item");
        for (var j = 0; j < items.length; j++) {
            items[j].addEventListener("click", function () {
                var viewName = this.getAttribute("data-view");
                if (AppState.activeView === viewName) {
                    AppState.activeView = null;
                } else {
                    AppState.activeView = viewName;
                }
                AppState.page = 0;
                renderCollections();
                renderViews();
                render();
            });
        }
    }

    // ── Database Filter ───────────────────────────────────────────────

    function initDbFilter() {
        var rows = query("SELECT DISTINCT source_db FROM bookmarks ORDER BY source_db");
        AppState.sourceDbs = rows.map(function (r) { return r.source_db; });

        var section = $("db-filter-section");
        var sel = $("db-filter-select");
        if (!section || !sel) return;

        if (AppState.sourceDbs.length <= 1) {
            section.hidden = true;
            return;
        }

        section.hidden = false;
        var html = '<option value="">All databases</option>';
        for (var i = 0; i < AppState.sourceDbs.length; i++) {
            html += '<option value="' + esc(AppState.sourceDbs[i]) + '">' + esc(AppState.sourceDbs[i]) + '</option>';
        }
        sel.innerHTML = html;

        sel.addEventListener("change", function () {
            AppState.activeSourceDb = this.value || null;
            AppState.page = 0;
            render();
        });
    }

    // ── Bookmark Detail Modal ─────────────────────────────────────────

    function showBookmarkModal(id) {
        var rows = query("SELECT * FROM bookmarks WHERE id = " + Number(id));
        if (rows.length === 0) return;
        var b = rows[0];
        var tags = tagsForBookmark(id);
        var media = mediaForBookmark(id);

        var modal = $("bookmark-modal");
        var title = $("modal-title");
        var body = $("modal-body");
        var link = $("modal-open-link");

        if (!modal || !body) return;

        title.textContent = b.title || b.url || "Bookmark";
        link.href = b.url || "#";

        var html = '<div class="modal-body">';

        // URL
        html += '<div class="modal-section"><h4>URL</h4>' +
            '<a class="modal-url" href="' + esc(b.url) + '" target="_blank" rel="noopener">' + esc(b.url) + '</a></div>';

        // Description
        if (b.description) {
            html += '<div class="modal-section"><h4>Description</h4>' +
                '<p class="modal-description">' + esc(b.description) + '</p></div>';
        }

        // Tags
        if (tags.length > 0) {
            html += '<div class="modal-section"><h4>Tags</h4><div class="modal-tags">';
            for (var i = 0; i < tags.length; i++) {
                var style = tags[i].color ? ' style="background:' + esc(tags[i].color) + '22;color:' + esc(tags[i].color) + '"' : "";
                html += '<span class="tag"' + style + ' data-tag="' + esc(tags[i].name) + '">' + esc(tags[i].name) + '</span>';
            }
            html += '</div></div>';
        }

        // Thumbnail
        if (media && media.thumbnail_url) {
            html += '<div class="modal-section"><h4>Preview</h4>' +
                '<img class="modal-thumbnail" src="' + esc(media.thumbnail_url) + '" alt=""></div>';
        }

        // Meta grid
        html += '<div class="modal-section"><h4>Details</h4><div class="modal-meta-grid">';
        html += metaItem("Added", fmtDate(b.added));
        html += metaItem("Visits", String(b.visit_count || 0));
        html += metaItem("Last Visited", b.last_visited ? fmtDate(b.last_visited) : "Never");
        html += metaItem("Starred", b.stars ? "Yes" : "No");
        html += metaItem("Pinned", b.pinned ? "Yes" : "No");
        html += metaItem("Archived", b.archived ? "Yes" : "No");
        var reachClass = b.reachable === 0 ? " danger" : (b.reachable === 1 ? " success" : "");
        var reachText = b.reachable === 0 ? "Unreachable" : (b.reachable === 1 ? "Reachable" : "Unknown");
        html += '<div class="meta-item"><span class="meta-label">Status</span><span class="meta-value' + reachClass + '">' + reachText + '</span></div>';
        html += metaItem("Domain", domain(b.url));

        if (b.source_db && b.source_db !== "default") {
            html += metaItem("Source", b.source_db);
        }

        if (media) {
            if (media.media_type) html += metaItem("Media Type", media.media_type);
            if (media.media_source) html += metaItem("Media Source", media.media_source);
            if (media.author_name) html += metaItem("Author", media.author_name);
        }
        html += '</div></div>';

        html += '</div>';
        body.innerHTML = html;

        // Tag click inside modal
        var tagEls = body.querySelectorAll(".tag[data-tag]");
        for (var t = 0; t < tagEls.length; t++) {
            tagEls[t].addEventListener("click", function () {
                var tag = this.getAttribute("data-tag");
                AppState.selectedTags[tag] = true;
                AppState.page = 0;
                closeModal(modal);
                renderTagCloud();
                render();
            });
        }

        modal.hidden = false;
    }

    function metaItem(label, value) {
        return '<div class="meta-item"><span class="meta-label">' + esc(label) +
            '</span><span class="meta-value">' + esc(value) + '</span></div>';
    }

    // ── Statistics Modal ──────────────────────────────────────────────

    function showStats() {
        var modal = $("stats-modal");
        var body = $("stats-body");
        if (!modal || !body) return;

        var total = scalar("SELECT COUNT(*) FROM bookmarks");
        var starred = scalar("SELECT COUNT(*) FROM bookmarks WHERE stars = 1");
        var unread = scalar("SELECT COUNT(*) FROM bookmarks WHERE visit_count = 0");
        var pinned = scalar("SELECT COUNT(*) FROM bookmarks WHERE pinned = 1");
        var archived = scalar("SELECT COUNT(*) FROM bookmarks WHERE archived = 1");
        var totalTags = scalar("SELECT COUNT(DISTINCT name) FROM tags");

        var html = '<div class="stats-grid">';
        html += statCard(total, "Total");
        html += statCard(starred, "Starred");
        html += statCard(unread, "Unread");
        html += statCard(pinned, "Pinned");
        html += statCard(archived, "Archived");
        html += statCard(totalTags, "Tags");
        html += '</div>';

        // Top domains
        var domains = query(
            "SELECT CASE WHEN url LIKE '%://%' THEN " +
            "REPLACE(REPLACE(SUBSTR(url, INSTR(url, '://') + 3), 'www.', ''), " +
            "SUBSTR(REPLACE(SUBSTR(url, INSTR(url, '://') + 3), 'www.', ''), " +
            "INSTR(REPLACE(SUBSTR(url, INSTR(url, '://') + 3), 'www.', ''), '/')), '') " +
            "ELSE url END AS dom, COUNT(*) AS c FROM bookmarks GROUP BY dom ORDER BY c DESC LIMIT 10"
        );
        if (domains.length > 0) {
            html += '<div class="stats-section"><h3>Top Domains</h3><div class="stats-list">';
            for (var i = 0; i < domains.length; i++) {
                html += '<div class="stats-list-item"><span class="name">' +
                    esc(domains[i].dom) + '</span><span class="count">' + domains[i].c + '</span></div>';
            }
            html += '</div></div>';
        }

        // Media types
        var mediaTypes = query(
            "SELECT media_type, COUNT(*) AS c FROM bookmark_media " +
            "WHERE media_type IS NOT NULL GROUP BY media_type ORDER BY c DESC"
        );
        if (mediaTypes.length > 0) {
            html += '<div class="stats-section"><h3>Media Types</h3><div class="stats-list">';
            for (var j = 0; j < mediaTypes.length; j++) {
                html += '<div class="stats-list-item"><span class="name">' +
                    esc(mediaTypes[j].media_type) + '</span><span class="count">' + mediaTypes[j].c + '</span></div>';
            }
            html += '</div></div>';
        }

        // Timeline (bookmarks per month)
        var timeline = query(
            "SELECT SUBSTR(added, 1, 7) AS month, COUNT(*) AS c FROM bookmarks " +
            "WHERE added IS NOT NULL GROUP BY month ORDER BY month DESC LIMIT 12"
        );
        if (timeline.length > 0) {
            timeline.reverse();
            var maxCount = 0;
            for (var k = 0; k < timeline.length; k++) {
                if (timeline[k].c > maxCount) maxCount = timeline[k].c;
            }
            html += '<div class="stats-section"><h3>Timeline (last 12 months)</h3>';
            html += '<div class="chart-timeline">';
            for (var m = 0; m < timeline.length; m++) {
                var pct = maxCount > 0 ? Math.round((timeline[m].c / maxCount) * 100) : 0;
                html += '<div class="chart-bar" style="height:' + Math.max(pct, 2) + '%">' +
                    '<span class="tooltip">' + esc(timeline[m].month) + ': ' + timeline[m].c + '</span></div>';
            }
            html += '</div>';
            html += '<div class="chart-labels"><span>' + esc(timeline[0].month) +
                '</span><span>' + esc(timeline[timeline.length - 1].month) + '</span></div>';
            html += '</div>';
        }

        body.innerHTML = html;
        modal.hidden = false;
    }

    function statCard(value, label) {
        return '<div class="stat-card"><div class="stat-value">' + esc(String(value)) +
            '</div><div class="stat-label">' + esc(label) + '</div></div>';
    }

    // ── SQL Query Box ─────────────────────────────────────────────────

    function showQueryModal() {
        var modal = $("query-modal");
        if (modal) {
            modal.hidden = false;
            var input = $("query-input");
            if (input) input.focus();
        }
    }

    function runUserQuery() {
        var input = $("query-input");
        var errorEl = $("query-error");
        var resultsEl = $("query-results");
        if (!input || !resultsEl) return;

        var sql = input.value.trim();
        if (!sql) return;

        // Read-only enforcement: first keyword must be SELECT, WITH, or EXPLAIN
        var firstWord = sql.split(/\s+/)[0].toUpperCase();
        if (!ALLOWED_QUERY_KEYWORDS[firstWord]) {
            if (errorEl) {
                errorEl.textContent = "Only SELECT, WITH, and EXPLAIN queries are allowed.";
                errorEl.hidden = false;
            }
            resultsEl.innerHTML = "";
            return;
        }

        if (errorEl) errorEl.hidden = true;

        try {
            var result = AppState.db.exec(sql);
            if (!result || result.length === 0) {
                resultsEl.innerHTML = '<p style="color:var(--text-secondary)">Query returned no results.</p>';
                return;
            }

            var cols = result[0].columns;
            var vals = result[0].values;

            var html = '<table><thead><tr>';
            for (var c = 0; c < cols.length; c++) {
                html += '<th>' + esc(cols[c]) + '</th>';
            }
            html += '</tr></thead><tbody>';

            for (var r = 0; r < vals.length; r++) {
                html += '<tr>';
                for (var v = 0; v < vals[r].length; v++) {
                    var cell = vals[r][v];
                    // Display BLOBs as [BLOB N bytes]
                    if (cell instanceof Uint8Array) {
                        cell = "[BLOB " + cell.length + " bytes]";
                    }
                    html += '<td>' + esc(cell) + '</td>';
                }
                html += '</tr>';
            }
            html += '</tbody></table>';
            resultsEl.innerHTML = html;
        } catch (e) {
            if (errorEl) {
                errorEl.textContent = e.message || String(e);
                errorEl.hidden = false;
            }
            resultsEl.innerHTML = "";
        }
    }

    // ── Shortcuts Modal ───────────────────────────────────────────────

    function showShortcuts() {
        var modal = $("shortcuts-modal");
        var body = $("shortcuts-body");
        if (!modal || !body) return;

        var html = '<div class="shortcuts-grid">';
        for (var i = 0; i < SHORTCUTS.length; i++) {
            var s = SHORTCUTS[i];
            html += '<div class="shortcut-item">' +
                '<kbd class="shortcut-key">' + esc(s.key) + '</kbd>' +
                '<span class="shortcut-desc">' + esc(s.desc) + '</span></div>';
        }
        html += '</div>';
        body.innerHTML = html;
        modal.hidden = false;
    }

    // ── Dark Mode ─────────────────────────────────────────────────────

    function applyTheme() {
        document.documentElement.setAttribute("data-theme", AppState.theme);
    }

    function toggleTheme() {
        AppState.theme = AppState.theme === "dark" ? "light" : "dark";
        localStorage.setItem("btk-theme", AppState.theme);
        applyTheme();
    }

    // ── View Mode ─────────────────────────────────────────────────────

    function setViewMode(mode) {
        AppState.viewMode = mode;
        document.body.className = "view-" + mode;

        var buttons = document.querySelectorAll(".view-btn");
        for (var i = 0; i < buttons.length; i++) {
            var btn = buttons[i];
            if (btn.getAttribute("data-view") === mode) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        }

        render();
    }

    // ── Modal Helpers ─────────────────────────────────────────────────

    function closeModal(modal) {
        if (modal) modal.hidden = true;
    }

    function closeAllModals() {
        var modals = document.querySelectorAll(".modal");
        for (var i = 0; i < modals.length; i++) {
            modals[i].hidden = true;
        }
    }

    function anyModalOpen() {
        var modals = document.querySelectorAll(".modal");
        for (var i = 0; i < modals.length; i++) {
            if (!modals[i].hidden) return true;
        }
        return false;
    }

    // ── Keyboard Navigation ───────────────────────────────────────────

    function getNavigableItems() {
        var container = $("bookmark-list");
        if (!container) return [];
        return container.querySelectorAll("[data-idx]");
    }

    function focusItem(idx) {
        var items = getNavigableItems();
        if (items.length === 0) return;

        // Remove previous focus
        for (var i = 0; i < items.length; i++) {
            items[i].classList.remove("focused");
        }

        if (idx < 0) idx = 0;
        if (idx >= items.length) idx = items.length - 1;
        AppState.focusIndex = idx;

        items[idx].classList.add("focused");
        items[idx].scrollIntoView({ block: "nearest" });
    }

    // ── Sidebar Toggle (Mobile) ───────────────────────────────────────

    function initSidebarToggle() {
        var toggle = $("sidebar-toggle");
        var sidebar = $("sidebar");
        var overlay = $("sidebar-overlay");
        if (!toggle || !sidebar) return;

        toggle.addEventListener("click", function () {
            sidebar.classList.toggle("open");
            if (overlay) overlay.hidden = !sidebar.classList.contains("open");
        });

        if (overlay) {
            overlay.addEventListener("click", function () {
                sidebar.classList.remove("open");
                overlay.hidden = true;
            });
        }
    }

    // ── Event Binding ─────────────────────────────────────────────────

    function bindEvents() {
        // Search
        var searchInput = $("search-input");
        if (searchInput) {
            var debounceTimer = null;
            searchInput.addEventListener("input", function () {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(function () {
                    AppState.searchQuery = searchInput.value.trim();
                    AppState.page = 0;
                    render();
                }, 200);
            });
        }

        // Sort
        var sortSelect = $("sort-select");
        if (sortSelect) {
            sortSelect.addEventListener("change", function () {
                AppState.sortKey = this.value;
                AppState.page = 0;
                render();
            });
        }

        // Starred / Pinned filter checkboxes
        var filterStarred = $("filter-starred");
        if (filterStarred) {
            filterStarred.addEventListener("change", function () {
                AppState.page = 0;
                render();
            });
        }
        var filterPinned = $("filter-pinned");
        if (filterPinned) {
            filterPinned.addEventListener("change", function () {
                AppState.page = 0;
                render();
            });
        }

        // Clear all filters
        var clearBtn = $("clear-filters");
        if (clearBtn) {
            clearBtn.addEventListener("click", function () {
                AppState.selectedTags = {};
                AppState.searchQuery = "";
                AppState.activeCollection = "all";
                AppState.activeView = null;
                AppState.activeSourceDb = null;
                AppState.page = 0;
                if (searchInput) searchInput.value = "";
                if (filterStarred) filterStarred.checked = false;
                if (filterPinned) filterPinned.checked = false;
                var dbSel = $("db-filter-select");
                if (dbSel) dbSel.value = "";
                renderCollections();
                renderViews();
                renderTagCloud();
                render();
            });
        }

        // View mode buttons
        var viewButtons = document.querySelectorAll(".view-btn");
        for (var i = 0; i < viewButtons.length; i++) {
            viewButtons[i].addEventListener("click", function () {
                setViewMode(this.getAttribute("data-view"));
            });
        }

        // Theme toggle
        var themeBtn = $("theme-toggle");
        if (themeBtn) {
            themeBtn.addEventListener("click", toggleTheme);
        }

        // Stats toggle
        var statsBtn = $("stats-toggle");
        if (statsBtn) {
            statsBtn.addEventListener("click", showStats);
        }

        // Stats close
        var statsClose = $("stats-close");
        if (statsClose) {
            statsClose.addEventListener("click", function () {
                closeModal($("stats-modal"));
            });
        }

        // Query toggle
        var queryBtn = $("query-toggle");
        if (queryBtn) {
            queryBtn.addEventListener("click", showQueryModal);
        }

        // Query run
        var queryRun = $("query-run");
        if (queryRun) {
            queryRun.addEventListener("click", runUserQuery);
        }

        // Query input enter
        var queryInput = $("query-input");
        if (queryInput) {
            queryInput.addEventListener("keydown", function (e) {
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                    runUserQuery();
                }
            });
        }

        // Query close
        var queryClose = $("query-close");
        if (queryClose) {
            queryClose.addEventListener("click", function () {
                closeModal($("query-modal"));
            });
        }

        // Shortcuts toggle
        var shortcutsBtn = $("shortcuts-toggle");
        if (shortcutsBtn) {
            shortcutsBtn.addEventListener("click", showShortcuts);
        }

        // Shortcuts close
        var shortcutsClose = $("shortcuts-close");
        if (shortcutsClose) {
            shortcutsClose.addEventListener("click", function () {
                closeModal($("shortcuts-modal"));
            });
        }

        // Bookmark modal close
        var modalClose = $("modal-close");
        if (modalClose) {
            modalClose.addEventListener("click", function () {
                closeModal($("bookmark-modal"));
            });
        }
        var modalCloseBtn = $("modal-close-btn");
        if (modalCloseBtn) {
            modalCloseBtn.addEventListener("click", function () {
                closeModal($("bookmark-modal"));
            });
        }

        // Close modals on overlay click
        var modals = document.querySelectorAll(".modal");
        for (var m = 0; m < modals.length; m++) {
            modals[m].addEventListener("click", function (e) {
                if (e.target === this) closeModal(this);
            });
        }

        // Keyboard shortcuts
        document.addEventListener("keydown", function (e) {
            var tag = e.target.tagName;
            var inInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

            // Escape always closes modals
            if (e.key === "Escape") {
                if (anyModalOpen()) {
                    closeAllModals();
                    return;
                }
            }

            // Skip shortcuts when typing in inputs (except Escape)
            if (inInput) return;

            switch (e.key) {
                case "/":
                    e.preventDefault();
                    if (searchInput) searchInput.focus();
                    break;
                case "j":
                    e.preventDefault();
                    focusItem(AppState.focusIndex + 1);
                    break;
                case "k":
                    e.preventDefault();
                    focusItem(AppState.focusIndex - 1);
                    break;
                case "Enter":
                    if (AppState.focusIndex >= 0) {
                        var items = getNavigableItems();
                        if (items[AppState.focusIndex]) {
                            var id = items[AppState.focusIndex].getAttribute("data-id");
                            showBookmarkModal(Number(id));
                        }
                    }
                    break;
                case "g":
                    setViewMode("grid");
                    break;
                case "l":
                    setViewMode("list");
                    break;
                case "t":
                    setViewMode("table");
                    break;
                case "m":
                    setViewMode("gallery");
                    break;
                case "d":
                    toggleTheme();
                    break;
                case "s":
                    showStats();
                    break;
                case "q":
                    showQueryModal();
                    break;
                case "?":
                    showShortcuts();
                    break;
            }
        });
    }

    // ── Initialization ────────────────────────────────────────────────

    // Initialize sql.js with the WASM binary
    var SQL = await initSqlJs({
        locateFile: function () { return WASM_URI; }
    });

    // Load the database bytes depending on packaging mode
    var dbBytes;
    if (LOAD_MODE === "embedded") {
        var el = document.getElementById("btk-db");
        var b64 = el.textContent.trim();
        var raw = atob(b64);
        dbBytes = new Uint8Array(raw.length);
        for (var i = 0; i < raw.length; i++) {
            dbBytes[i] = raw.charCodeAt(i);
        }
    } else {
        var resp = await fetch("export.db");
        var buf = await resp.arrayBuffer();
        dbBytes = new Uint8Array(buf);
    }

    var db = new SQL.Database(dbBytes);
    AppState.db = db;

    // Apply saved theme
    applyTheme();

    // Initialize UI components
    initSidebarToggle();
    initDbFilter();
    renderCollections();
    renderViews();
    renderTagCloud();
    bindEvents();

    // Initial render
    render();
})();
