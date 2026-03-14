"""
HTML template assembly for sql.js HTML-app export.

Provides two packaging modes:
- Embedded: single self-contained HTML file with inlined assets
- Directory: multi-file output with external assets loaded via fetch()
"""
import base64
import json
import shutil
from pathlib import Path
from typing import Optional

from btk.html_app.builder import encode_export_db

# Resolve assets directory relative to this file
_ASSETS_DIR = Path(__file__).parent / "assets"


def _read_asset(name: str) -> str:
    """Read a text asset file from the assets directory."""
    return (_ASSETS_DIR / name).read_text(encoding="utf-8")


def _read_asset_bytes(name: str) -> bytes:
    """Read a binary asset file from the assets directory."""
    return (_ASSETS_DIR / name).read_bytes()


def _build_html(
    *,
    css_block: str,
    sqljs_block: str,
    wasm_uri_js: str,
    load_mode_js: str,
    db_block: str,
    views_json: str,
    app_js_block: str,
) -> str:
    """Build the full HTML document.

    Args:
        css_block: CSS content (either inlined or <link> tag).
        sqljs_block: sql-wasm.js content (either inlined or <script src>).
        wasm_uri_js: JavaScript expression for WASM_URI variable.
        load_mode_js: JavaScript string for LOAD_MODE variable.
        db_block: Base64-encoded DB in <script> tag, or empty for directory mode.
        views_json: JSON string of view definitions.
        app_js_block: app.js content (either inlined or <script src>).
    """
    return f'''<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bookmark Viewer</title>
    <style>{css_block}</style>
</head>
<body class="view-grid">
    <div class="app-container">
        <header id="app-header">
            <button id="sidebar-toggle" aria-label="Toggle sidebar">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M3 12h18M3 6h18M3 18h18"/>
                </svg>
            </button>
            <div class="header-brand">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
                </svg>
                <span>Bookmarks</span>
            </div>
            <div class="search-container">
                <svg class="search-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
                </svg>
                <input type="search" id="search-input" placeholder="Search bookmarks... (press /)" autocomplete="off">
            </div>
            <div class="view-switcher">
                <button class="view-btn active" data-view="grid" aria-label="Grid view" title="Grid view (g)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
                        <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
                    </svg>
                </button>
                <button class="view-btn" data-view="list" aria-label="List view" title="List view (l)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/>
                        <line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/>
                        <line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
                    </svg>
                </button>
                <button class="view-btn" data-view="table" aria-label="Table view" title="Table view (t)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                        <line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/>
                        <line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/>
                    </svg>
                </button>
                <button class="view-btn" data-view="gallery" aria-label="Gallery view" title="Gallery view (m)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                        <circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
                    </svg>
                </button>
            </div>
            <div class="header-actions">
                <span id="bookmark-count" class="bookmark-count">0 bookmarks</span>
                <button id="query-toggle" aria-label="SQL Query" title="SQL Query (q)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
                    </svg>
                </button>
                <button id="stats-toggle" aria-label="Show statistics" title="Statistics (s)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/>
                        <line x1="6" y1="20" x2="6" y2="14"/>
                    </svg>
                </button>
                <button id="shortcuts-toggle" aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="2" y="4" width="20" height="16" rx="2" ry="2"/>
                        <line x1="6" y1="8" x2="6.01" y2="8"/><line x1="10" y1="8" x2="10.01" y2="8"/>
                        <line x1="14" y1="8" x2="14.01" y2="8"/><line x1="18" y1="8" x2="18.01" y2="8"/>
                        <line x1="8" y1="12" x2="8.01" y2="12"/><line x1="12" y1="12" x2="12.01" y2="12"/>
                        <line x1="16" y1="12" x2="16.01" y2="12"/>
                        <line x1="7" y1="16" x2="17" y2="16"/>
                    </svg>
                </button>
                <button id="theme-toggle" aria-label="Toggle theme" title="Toggle theme (d)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
                    </svg>
                </button>
            </div>
        </header>

        <div id="sidebar-overlay" class="sidebar-overlay" hidden></div>

        <aside id="sidebar">
            <div class="sidebar-section collections-section">
                <h3>Collections</h3>
                <div id="collections-list">
                    <!-- Rendered by JavaScript -->
                </div>
            </div>

            <div class="sidebar-section views-section" id="views-section" hidden>
                <h3>Curated Views</h3>
                <div id="views-list">
                    <!-- Rendered by JavaScript -->
                </div>
            </div>

            <div class="sidebar-section" id="db-filter-section" hidden>
                <h3>Database</h3>
                <select id="db-filter-select">
                    <option value="">All databases</option>
                    <!-- Populated by JavaScript when multiple source_db values -->
                </select>
            </div>

            <div class="sidebar-section">
                <h3>Sort By</h3>
                <select id="sort-select">
                    <option value="added-desc">Date Added (newest)</option>
                    <option value="added-asc">Date Added (oldest)</option>
                    <option value="title-asc">Title (A-Z)</option>
                    <option value="title-desc">Title (Z-A)</option>
                    <option value="visits-desc">Most Visited</option>
                    <option value="visited-desc">Last Visited</option>
                    <option value="stars-desc">Most Stars</option>
                </select>
            </div>

            <div class="sidebar-section">
                <h3>Filters</h3>
                <div class="filter-checkboxes">
                    <label>
                        <input type="checkbox" id="filter-starred">
                        <span>Starred only</span>
                    </label>
                    <label>
                        <input type="checkbox" id="filter-pinned">
                        <span>Pinned only</span>
                    </label>
                </div>
            </div>

            <div class="sidebar-section">
                <h3>Tags</h3>
                <div id="tag-cloud"></div>
                <button id="clear-filters" class="clear-filters">Clear all filters</button>
            </div>
        </aside>

        <main id="main-content">
            <div id="bookmark-list"></div>
        </main>
    </div>

    <div id="bookmark-modal" class="modal" hidden>
        <div class="modal-content">
            <div class="modal-header">
                <h2 id="modal-title">Bookmark Details</h2>
                <button id="modal-close" class="modal-close">&times;</button>
            </div>
            <div id="modal-body"></div>
            <div class="modal-actions">
                <a id="modal-open-link" href="#" target="_blank" rel="noopener" class="btn btn-primary">
                    Open Link
                </a>
                <button id="modal-close-btn" class="btn btn-secondary">Close</button>
            </div>
        </div>
    </div>

    <div id="stats-modal" class="modal" hidden>
        <div class="modal-content stats-dashboard">
            <div class="modal-header">
                <h2>Statistics</h2>
                <button id="stats-close" class="modal-close">&times;</button>
            </div>
            <div id="stats-body">
                <!-- Rendered by JavaScript -->
            </div>
        </div>
    </div>

    <div id="shortcuts-modal" class="modal" hidden>
        <div class="modal-content shortcuts-content">
            <div class="modal-header">
                <h2>Keyboard Shortcuts</h2>
                <button id="shortcuts-close" class="modal-close">&times;</button>
            </div>
            <div id="shortcuts-body">
                <!-- Rendered by JavaScript -->
            </div>
        </div>
    </div>

    <div id="query-modal" class="modal" hidden>
        <div class="modal-content query-content">
            <div class="modal-header">
                <h2>SQL Query</h2>
                <button id="query-close" class="modal-close">&times;</button>
            </div>
            <div class="query-input-area">
                <textarea id="query-input" rows="3" placeholder="SELECT * FROM bookmarks LIMIT 10"></textarea>
                <button id="query-run" class="btn btn-primary">Run</button>
            </div>
            <div id="query-error" class="query-error" hidden></div>
            <div id="query-results"></div>
        </div>
    </div>

    <script id="btk-views" type="application/json">{views_json}</script>
    {db_block}
    {sqljs_block}
    <script>
    var WASM_URI = {wasm_uri_js};
    var LOAD_MODE = {load_mode_js};
    </script>
    {app_js_block}
</body>
</html>'''


def assemble_embedded(db_bytes: bytes, views: Optional[dict] = None) -> str:
    """Build a single self-contained HTML file with all assets inlined.

    Args:
        db_bytes: Raw SQLite database bytes from build_export_db().
        views: Optional view definitions for sidebar collections.

    Returns:
        Complete HTML string ready to write to a file.
    """
    css_content = _read_asset("app.css")
    sqljs_content = _read_asset("sql-wasm.js")
    appjs_content = _read_asset("app.js")
    wasm_bytes = _read_asset_bytes("sql-wasm.wasm")

    # Base64-encode WASM for data URI
    wasm_b64 = base64.b64encode(wasm_bytes).decode("ascii")
    wasm_data_uri = f"data:application/wasm;base64,{wasm_b64}"

    # Base64-encode the export database
    db_b64 = encode_export_db(db_bytes)

    views_json = json.dumps(views or {}, ensure_ascii=False)

    return _build_html(
        css_block=css_content,
        sqljs_block=f"<script>{sqljs_content}</script>",
        wasm_uri_js=json.dumps(wasm_data_uri),
        load_mode_js=json.dumps("embedded"),
        db_block=f'<script type="application/octet-stream" id="btk-db">{db_b64}</script>',
        views_json=views_json,
        app_js_block=f"<script>{appjs_content}</script>",
    )


def assemble_directory(
    db_bytes: bytes,
    output_dir: Path,
    views: Optional[dict] = None,
) -> None:
    """Write a multi-file HTML export to a directory.

    Creates:
        output_dir/index.html   - HTML with <script src="..."> references
        output_dir/sql-wasm.js  - sql.js loader
        output_dir/sql-wasm.wasm - sql.js WASM binary
        output_dir/export.db    - SQLite export database

    Args:
        db_bytes: Raw SQLite database bytes from build_export_db().
        output_dir: Target directory (created if it does not exist).
        views: Optional view definitions for sidebar collections.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    css_content = _read_asset("app.css")
    appjs_content = _read_asset("app.js")
    views_json = json.dumps(views or {}, ensure_ascii=False)

    # Copy vendored sql.js assets
    shutil.copy2(_ASSETS_DIR / "sql-wasm.js", output_dir / "sql-wasm.js")
    shutil.copy2(_ASSETS_DIR / "sql-wasm.wasm", output_dir / "sql-wasm.wasm")

    # Write the export database
    (output_dir / "export.db").write_bytes(db_bytes)

    # Build index.html with external script references and fetch-based loading
    html = _build_html(
        css_block=css_content,
        sqljs_block='<script src="sql-wasm.js"></script>',
        wasm_uri_js=json.dumps("sql-wasm.wasm"),
        load_mode_js=json.dumps("directory"),
        db_block="",
        views_json=views_json,
        app_js_block=f"<script>{appjs_content}</script>",
    )

    (output_dir / "index.html").write_text(html, encoding="utf-8")
