/**
 * btk HTML-app JavaScript — sql.js query engine (placeholder).
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

    // Initialise sql.js with the WASM binary
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

    // Display bookmark count
    var stmt = db.prepare("SELECT COUNT(*) FROM bookmarks");
    stmt.step();
    var count = stmt.get()[0];
    stmt.free();
    var countEl = document.getElementById("bookmark-count");
    if (countEl) {
        countEl.textContent = count + " bookmarks";
    }
})();
